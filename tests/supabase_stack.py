"""A real, local Supabase for testing Mike's accounts end to end.

    python -m tests.supabase_stack up      # start it (prints URL and keys)
    python -m tests.supabase_stack down    # remove it

Runs the same open-source services a hosted Supabase project runs — Postgres
(supabase/postgres), Auth (GoTrue), the REST API (PostgREST) and Storage — in
Docker, plus Mailpit to catch the emails Auth sends, so tests can read the
6-digit codes a real person would type. A small gateway on 127.0.0.1:54321
routes /auth/v1, /rest/v1 and /storage/v1 the way Supabase's API gateway does,
and serves supabase/templates/ so Auth sends Mike's real email templates.

Then supabase/migrations/*.sql is applied as the `postgres` role — the role
the dashboard's SQL editor uses — so a migration that works here has the
privileges it needs there too.

Nothing here ships in the app. tests/test_account_e2e.py skips when Docker
isn't available.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
NET = "mike-sb"
PREFIX = "mike-sb-"
GATEWAY_PORT = 54321
MAIL_PORT = 54325
PG_PASSWORD = "postgres"
JWT_SECRET = "mike-local-jwt-secret-with-at-least-32-characters"

IMAGES = {
    "db": "supabase/postgres:15.14.1.176",
    "auth": "supabase/gotrue:v2.197.0",
    "rest": "postgrest/postgrest:v12.2.3",
    "storage": "supabase/storage-api:v1.79.19",
    "mail": "axllent/mailpit:v1.31",
}
PORTS = {"auth": 54331, "rest": 54332, "storage": 54333}

URL = f"http://127.0.0.1:{GATEWAY_PORT}"


def _jwt(payload: dict) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    sig = hmac.new(JWT_SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{b64(sig)}"


ANON_KEY = _jwt({"role": "anon", "iss": "supabase", "iat": 1700000000, "exp": 2100000000})
SERVICE_KEY = _jwt({"role": "service_role", "iss": "supabase", "iat": 1700000000, "exp": 2100000000})


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def _running(name: str) -> bool:
    r = _docker("inspect", "-f", "{{.State.Running}}", PREFIX + name, check=False)
    return r.returncode == 0 and r.stdout.strip() == "true"


def _psql(sql: str, user: str = "supabase_admin") -> str:
    r = subprocess.run(
        ["docker", "exec", "-i", "-e", f"PGPASSWORD={PG_PASSWORD}", PREFIX + "db",
         "psql", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-U", user, "-d", "postgres",
         "-At"],
        input=sql, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"psql as {user} failed:\n{r.stderr}")
    return r.stdout


def _wait(check, what: str, timeout: float = 120) -> None:
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            if check():
                return
        except Exception as exc:  # still starting
            last = exc
        time.sleep(1)
    raise RuntimeError(f"{what} did not come up in {timeout:.0f}s ({last})")


# ── gateway ──────────────────────────────────────────────────────────────

_ROUTES = {
    "/auth/v1": f"http://127.0.0.1:{PORTS['auth']}",
    "/rest/v1": f"http://127.0.0.1:{PORTS['rest']}",
    "/storage/v1": f"http://127.0.0.1:{PORTS['storage']}",
}
_HOP = {"connection", "keep-alive", "transfer-encoding", "content-encoding",
        "content-length", "host", "upgrade"}


class _Gateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):  # quiet
        pass

    def _forward(self):
        if self.path.startswith("/templates/"):
            f = REPO / "supabase" / "templates" / Path(self.path).name
            body = f.read_bytes() if f.exists() else b""
            self.send_response(200 if body else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        for prefix, upstream in _ROUTES.items():
            if self.path.startswith(prefix):
                break
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        # Like Supabase's gateway: every API call must carry the project key.
        if not self.headers.get("apikey") and "/object/public/" not in self.path \
                and not self.path.startswith("/auth/v1/callback") \
                and not self.path.startswith("/auth/v1/authorize"):
            body = b'{"message":"No API key found in request"}'
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in _HOP}
        resp = requests.request(self.command, upstream + self.path[len(prefix):],
                                headers=headers, data=data, allow_redirects=False,
                                timeout=60)
        body = resp.content
        self.send_response(resp.status_code)
        for k, v in resp.headers.items():
            if k.lower() not in _HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _forward


_gateway: ThreadingHTTPServer | None = None


def start_gateway() -> None:
    global _gateway
    if _gateway is not None:
        return
    try:
        _gateway = ThreadingHTTPServer(("0.0.0.0", GATEWAY_PORT), _Gateway)
    except OSError:
        # Already served — by `python -m tests.supabase_stack up` in another
        # terminal. Use that one.
        return
    threading.Thread(target=_gateway.serve_forever, daemon=True).start()


def stop_gateway() -> None:
    global _gateway
    if _gateway is not None:
        _gateway.shutdown()
        _gateway.server_close()
        _gateway = None


# ── services ─────────────────────────────────────────────────────────────

def _auth_env() -> list[str]:
    tpl = f"http://host.docker.internal:{GATEWAY_PORT}/templates"
    env = {
        "GOTRUE_API_HOST": "0.0.0.0",
        "GOTRUE_API_PORT": "9999",
        "API_EXTERNAL_URL": f"{URL}/auth/v1",
        "GOTRUE_DB_DRIVER": "postgres",
        "GOTRUE_DB_DATABASE_URL": f"postgres://supabase_auth_admin:{PG_PASSWORD}@{PREFIX}db:5432/postgres",
        "GOTRUE_SITE_URL": "http://127.0.0.1:3000",
        "GOTRUE_URI_ALLOW_LIST": "http://127.0.0.1:*/auth/callback",
        "GOTRUE_DISABLE_SIGNUP": "false",
        "GOTRUE_JWT_ADMIN_ROLES": "service_role",
        "GOTRUE_JWT_AUD": "authenticated",
        "GOTRUE_JWT_DEFAULT_GROUP_NAME": "authenticated",
        "GOTRUE_JWT_EXP": "3600",
        "GOTRUE_JWT_SECRET": JWT_SECRET,
        "GOTRUE_EXTERNAL_EMAIL_ENABLED": "true",
        "GOTRUE_MAILER_AUTOCONFIRM": "false",
        "GOTRUE_MAILER_SECURE_EMAIL_CHANGE_ENABLED": "true",
        "GOTRUE_SMTP_ADMIN_EMAIL": "no-reply@mike.local",
        "GOTRUE_SMTP_HOST": f"{PREFIX}mail",
        "GOTRUE_SMTP_PORT": "1025",
        # No SMTP credentials: Go refuses to send them over an unencrypted
        # connection, and Mailpit doesn't need them.
        "GOTRUE_SMTP_SENDER_NAME": "Mike",
        "GOTRUE_SMTP_MAX_FREQUENCY": "1s",
        "GOTRUE_RATE_LIMIT_EMAIL_SENT": "10000",
        "GOTRUE_RATE_LIMIT_VERIFY": "10000",
        "GOTRUE_RATE_LIMIT_TOKEN_REFRESH": "10000",
        "GOTRUE_RATE_LIMIT_OTP": "10000",
        "GOTRUE_PASSWORD_MIN_LENGTH": "8",
        "GOTRUE_MAILER_TEMPLATES_CONFIRMATION": f"{tpl}/confirmation.html",
        "GOTRUE_MAILER_TEMPLATES_MAGIC_LINK": f"{tpl}/magic_link.html",
        "GOTRUE_MAILER_TEMPLATES_RECOVERY": f"{tpl}/recovery.html",
        "GOTRUE_MAILER_TEMPLATES_EMAIL_CHANGE": f"{tpl}/email_change.html",
        "GOTRUE_MAILER_TEMPLATES_REAUTHENTICATION": f"{tpl}/reauthentication.html",
        "GOTRUE_MAILER_SUBJECTS_CONFIRMATION": "Your Mike code",
        "GOTRUE_MAILER_SUBJECTS_MAGIC_LINK": "Your Mike sign-in code",
        "GOTRUE_MAILER_SUBJECTS_RECOVERY": "Reset your Mike password",
        "GOTRUE_MAILER_SUBJECTS_EMAIL_CHANGE": "Confirm your new email for Mike",
        "GOTRUE_MAILER_SUBJECTS_REAUTHENTICATION": "Confirm it's you",
        # A Google provider with placeholder credentials: enough to check that
        # Mike's sign-in URL starts a real PKCE flow (Google itself can't be
        # reached from a test).
        "GOTRUE_EXTERNAL_GOOGLE_ENABLED": "true",
        "GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID": "local-test-client.apps.googleusercontent.com",
        "GOTRUE_EXTERNAL_GOOGLE_SECRET": "local-test-secret",
        "GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI": f"{URL}/auth/v1/callback",
    }
    out = []
    for k, v in env.items():
        out += ["-e", f"{k}={v}"]
    return out


def _extra_ca() -> list[str]:
    """Where outbound HTTPS is intercepted by a proxy with its own CA (some CI
    and cloud sandboxes), let Auth trust it too — it fetches Google's OpenID
    configuration when a Google sign-in starts."""
    bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE") or ""
    if not bundle or not os.path.exists(bundle):
        return []
    return ["-v", f"{bundle}:/etc/ssl/certs/extra-ca.crt:ro",
            "-e", "SSL_CERT_FILE=/etc/ssl/certs/extra-ca.crt"]


def up(verbose: bool = True) -> dict:
    """Start the stack (idempotent) and apply the migrations. Returns its config."""
    say = print if verbose else (lambda *a, **k: None)
    _docker("network", "create", NET, check=False)
    start_gateway()

    if not _running("db"):
        _docker("rm", "-f", PREFIX + "db", check=False)
        say("starting postgres…")
        _docker("run", "-d", "--name", PREFIX + "db", "--network", NET,
                "-e", f"POSTGRES_PASSWORD={PG_PASSWORD}",
                "-e", f"JWT_SECRET={JWT_SECRET}",
                IMAGES["db"])
    _wait(lambda: _psql("select 1").strip() == "1", "postgres", 180)
    _psql(f"""
        alter user authenticator with password '{PG_PASSWORD}';
        alter user supabase_auth_admin with password '{PG_PASSWORD}';
        alter user supabase_storage_admin with password '{PG_PASSWORD}';
        alter user postgres with password '{PG_PASSWORD}';
    """)

    if not _running("mail"):
        _docker("rm", "-f", PREFIX + "mail", check=False)
        say("starting mailpit…")
        _docker("run", "-d", "--name", PREFIX + "mail", "--network", NET,
                "-p", f"127.0.0.1:{MAIL_PORT}:8025",
                "-e", "MP_SMTP_AUTH_ACCEPT_ANY=1", "-e", "MP_SMTP_AUTH_ALLOW_INSECURE=1",
                IMAGES["mail"])

    if not _running("auth"):
        _docker("rm", "-f", PREFIX + "auth", check=False)
        say("starting auth…")
        _docker("run", "-d", "--name", PREFIX + "auth", "--network", NET,
                "--add-host", "host.docker.internal:host-gateway",
                *_extra_ca(), "-p", f"127.0.0.1:{PORTS['auth']}:9999", *_auth_env(),
                IMAGES["auth"])
    _wait(lambda: requests.get(f"http://127.0.0.1:{PORTS['auth']}/health", timeout=3).ok,
          "auth", 120)

    if not _running("rest"):
        _docker("rm", "-f", PREFIX + "rest", check=False)
        say("starting rest…")
        _docker("run", "-d", "--name", PREFIX + "rest", "--network", NET,
                "-p", f"127.0.0.1:{PORTS['rest']}:3000",
                "-e", f"PGRST_DB_URI=postgres://authenticator:{PG_PASSWORD}@{PREFIX}db:5432/postgres",
                "-e", "PGRST_DB_SCHEMAS=public,storage,graphql_public",
                "-e", "PGRST_DB_ANON_ROLE=anon",
                "-e", f"PGRST_JWT_SECRET={JWT_SECRET}",
                "-e", "PGRST_DB_USE_LEGACY_GUCS=false",
                IMAGES["rest"])

    if not _running("storage"):
        _docker("rm", "-f", PREFIX + "storage", check=False)
        say("starting storage…")
        _docker("run", "-d", "--name", PREFIX + "storage", "--network", NET,
                "-p", f"127.0.0.1:{PORTS['storage']}:5000",
                "-e", f"ANON_KEY={ANON_KEY}", "-e", f"SERVICE_KEY={SERVICE_KEY}",
                "-e", f"POSTGREST_URL=http://{PREFIX}rest:3000",
                "-e", f"PGRST_JWT_SECRET={JWT_SECRET}", "-e", f"AUTH_JWT_SECRET={JWT_SECRET}",
                "-e", f"DATABASE_URL=postgres://supabase_storage_admin:{PG_PASSWORD}@{PREFIX}db:5432/postgres",
                "-e", "FILE_SIZE_LIMIT=52428800", "-e", "STORAGE_BACKEND=file",
                "-e", "FILE_STORAGE_BACKEND_PATH=/var/lib/storage",
                "-e", "TENANT_ID=stub", "-e", "REGION=stub", "-e", "GLOBAL_S3_BUCKET=stub",
                "-e", "ENABLE_IMAGE_TRANSFORMATION=false",
                IMAGES["storage"])
    _wait(lambda: requests.get(f"http://127.0.0.1:{PORTS['storage']}/status", timeout=3).ok,
          "storage", 180)
    _wait(lambda: _psql("select to_regclass('storage.objects') is not null "
                        "and to_regclass('auth.users') is not null").strip() == "t",
          "auth and storage migrations", 120)

    for sql in sorted((REPO / "supabase" / "migrations").glob("*.sql")):
        say(f"applying {sql.name} as postgres…")
        _psql(sql.read_text(encoding="utf-8"), user="postgres")
    # PostgREST caches the schema; tell it about the new table and function.
    _psql("notify pgrst, 'reload schema';")
    _wait(lambda: requests.get(f"{URL}/rest/v1/", headers={"apikey": ANON_KEY}, timeout=3).ok,
          "rest", 60)
    time.sleep(1)
    cfg = {"url": URL, "anon_key": ANON_KEY, "service_key": SERVICE_KEY,
           "mail": f"http://127.0.0.1:{MAIL_PORT}"}
    say(json.dumps(cfg, indent=2))
    return cfg


def down() -> None:
    stop_gateway()
    for name in ("storage", "rest", "auth", "mail", "db"):
        _docker("rm", "-f", PREFIX + name, check=False)
    _docker("network", "rm", NET, check=False)


# ── mail ─────────────────────────────────────────────────────────────────

def latest_code(to: str, after: float = 0.0, timeout: float = 20) -> str:
    """The 6-digit code in the newest email sent to `to` (after a timestamp)."""
    import re
    mail = f"http://127.0.0.1:{MAIL_PORT}/api/v1"
    end = time.time() + timeout
    while time.time() < end:
        msgs = requests.get(f"{mail}/search", params={"query": f"to:{to}"}, timeout=5).json()
        for m in msgs.get("messages", []):
            created = m.get("Created", "")
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = time.time()
            if ts + 0.5 < after:
                continue
            body = requests.get(f"{mail}/message/{m['ID']}", timeout=5).json()
            text = body.get("Text") or body.get("HTML") or ""
            found = re.search(r"\b(\d{6})\b", text)
            if found:
                return found.group(1)
        time.sleep(0.5)
    raise AssertionError(f"no code emailed to {to}")


def mail_subjects(to: str) -> list[str]:
    mail = f"http://127.0.0.1:{MAIL_PORT}/api/v1"
    msgs = requests.get(f"{mail}/search", params={"query": f"to:{to}"}, timeout=5).json()
    return [m.get("Subject", "") for m in msgs.get("messages", [])]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "up"
    if cmd == "up":
        up()
        print(f"gateway on {URL} — Ctrl+C to stop the gateway (containers keep running)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    elif cmd == "down":
        down()
