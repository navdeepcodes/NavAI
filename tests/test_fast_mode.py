"""Fast mode: the student's own Cloudflare account first, the local model behind it."""
import threading
import time
import urllib.request
from urllib.parse import parse_qs, urlparse

import pytest

from tests import _isolate  # noqa: F401 -- before any brain/config import

from account import cloudflare
from brain.providers import workers_ai_provider as fast
from brain.providers.base import BrainError, Capabilities, ChatResult, StreamEvent


class _Local:
    name = "engine"

    def __init__(self):
        self.calls = 0
        self.warmed = False

    def capabilities(self):
        return Capabilities(model="local", provider="engine", declared_text=True,
                            declared_vision=True, declared_tools=True)

    def stream(self, messages, tools=None, *, cancel=None):
        self.calls += 1
        yield StreamEvent(kind="text", text="local")
        yield StreamEvent(kind="done")

    def complete(self, messages, tools=None, *, max_tokens=None):
        self.calls += 1
        return ChatResult(text="local")

    def describe_image(self, *a, **k):
        return "seen here"

    def health(self):
        return None

    def translate_error(self, exc):
        return BrainError(kind="unknown", message=str(exc))

    def warm_prefix(self, system, tools):
        self.warmed = True
        return "done"


def _provider(monkeypatch, *, on=True, cloud_events=None):
    local = _Local()
    p = fast.WorkersAIProvider(local, "@cf/qwen/qwen3-30b-a3b-fp8")
    monkeypatch.setattr(fast, "fast_mode_on", lambda: on)
    monkeypatch.setattr(fast, "_allowance_gone_until", 0.0)
    monkeypatch.setattr(p._cloud, "_key", lambda: "token")
    sent = []

    def cloud_stream(messages, tools=None, *, cancel=None):
        sent.append(messages)
        yield from (cloud_events or [StreamEvent(kind="text", text="cloud"),
                                     StreamEvent(kind="done")])

    monkeypatch.setattr(p._cloud, "stream", cloud_stream)
    return p, local, sent


def _texts(events):
    return "".join(e.text or "" for e in events if e.kind == "text")


def test_not_connected_means_everything_is_local(monkeypatch):
    p, local, sent = _provider(monkeypatch, on=False)
    assert _texts(p.stream([{"role": "user", "content": "hi"}])) == "local"
    assert sent == [] and p.capabilities().provider == "engine"


def test_connected_the_cloud_answers(monkeypatch):
    p, local, sent = _provider(monkeypatch)
    assert _texts(p.stream([{"role": "user", "content": "hi"}])) == "cloud"
    assert local.calls == 0 and p.status() == "on"


def test_a_cloud_failure_before_any_answer_goes_to_the_local_model(monkeypatch):
    err = BrainError(kind="unavailable", message="down", detail="connection refused")
    p, local, sent = _provider(monkeypatch, cloud_events=[StreamEvent(kind="error", error=err)])
    assert _texts(p.stream([{"role": "user", "content": "hi"}])) == "local"
    # and it stays local for a while, without asking the cloud each turn
    assert _texts(p.stream([{"role": "user", "content": "again"}])) == "local"
    assert len(sent) == 1 and p.status() == "resting"


def test_the_days_allowance_used_up_rests_until_it_resets(monkeypatch):
    err = BrainError(kind="timeout", message="limit",
                     detail='{"code": 4006, "message": "you have used up your daily free '
                            'allocation of 10,000 neurons"}')
    p, local, _ = _provider(monkeypatch, cloud_events=[StreamEvent(kind="error", error=err)])
    list(p.stream([{"role": "user", "content": "hi"}]))
    assert p._resting_until == fast._next_utc_midnight()
    assert time.gmtime(p._resting_until).tm_hour == 0


def test_screenshots_stay_on_the_computer(monkeypatch):
    p, _, _ = _provider(monkeypatch)
    assert p.describe_image("shot.png", "what's here?") == "seen here"
    assert p.capabilities().can("vision")      # vision is the local model's


def test_the_local_model_is_not_loaded_at_startup_while_the_cloud_answers(monkeypatch):
    p, local, _ = _provider(monkeypatch)
    assert p.warm_prefix("sys", []) == "cloud" and not local.warmed
    p, local, _ = _provider(monkeypatch, on=False)
    assert p.warm_prefix("sys", []) == "done" and local.warmed


def test_anything_else_is_the_local_brains(monkeypatch):
    p, local, _ = _provider(monkeypatch)
    local.num_ctx = 16384
    assert p.num_ctx == 16384


def test_the_cloud_gets_one_system_message_and_no_thinking():
    msgs = [{"role": "system", "content": "Mike"}, {"role": "system", "content": "ctx"},
            {"role": "user", "content": "hi"}]
    body = fast._Cloud("@cf/google/gemma-4-26b-a4b-it")._payload(msgs, None, stream=True)
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_a_number_streamed_as_a_number_is_still_text():
    from brain.providers.openai_compatible import _text
    assert _text(84) == "84" and _text(0) == "0" and _text(None) == "" and _text("hi") == "hi"


# ── when the local model takes over ──────────────────────────────────────

def _failing_cloud(monkeypatch, detail="connection refused"):
    err = BrainError(kind="unavailable", message="down", detail=detail)
    p, local, _ = _provider(monkeypatch, cloud_events=[StreamEvent(kind="error", error=err)])
    primed = []
    local.warm_prefix = lambda system, tools: primed.append((system, tools)) or "restored"
    return p, local, primed


def test_the_local_model_restores_its_saved_prompt_before_answering(monkeypatch):
    """Measured: the first local answer after a switch took 100s -- the engine
    started cold and read all of Mike's prompt again."""
    p, local, primed = _failing_cloud(monkeypatch)
    msgs = [{"role": "system", "content": "Mike's fixed prompt"}, {"role": "user", "content": "hi"}]
    list(p.stream(msgs, [{"t": 1}]))
    list(p.stream(msgs, [{"t": 1}]))
    assert primed == [("Mike's fixed prompt", [{"t": 1}])], "once, before the first local answer"


def test_a_switch_to_the_local_model_is_said_once(monkeypatch):
    p, local, _ = _failing_cloud(
        monkeypatch, '{"message":"you have used up your daily free allocation of 10,000 neurons"}')
    list(p.stream([{"role": "user", "content": "hi"}]))
    notice = p.take_notice()
    assert "allowance is used up" in notice and ("AM" in notice or "PM" in notice)
    assert p.take_notice() is None
    list(p.stream([{"role": "user", "content": "again"}]))
    assert p.take_notice() is None, "not every turn"


def test_fast_mode_coming_back_is_said(monkeypatch):
    p, local, _ = _failing_cloud(monkeypatch)
    list(p.stream([{"role": "user", "content": "hi"}]))
    p.take_notice()
    p._resting_until = 0.0
    monkeypatch.setattr(p._cloud, "stream", lambda *a, **k: iter(
        [StreamEvent(kind="text", text="cloud"), StreamEvent(kind="done")]))
    list(p.stream([{"role": "user", "content": "hi"}]))
    assert p.take_notice() == "Fast mode is back."


class _Engine:
    def __init__(self, saved):
        self.saved, self.calls = saved, []

    def has_prefix(self, system, tools):
        return self.saved

    def running(self):
        return False

    def start(self, background=False):
        self.calls.append(("start", background))

    def ensure_prefix(self, system, tools):
        self.calls.append("read")

    def stop(self):
        self.calls.append("stop")


def test_a_missing_local_prompt_is_prepared_in_the_background_and_put_away(monkeypatch):
    p, local, _ = _provider(monkeypatch)
    local._engine = _Engine(saved=False)
    monkeypatch.setattr(fast, "PREPARE_AFTER", 0)
    p._prepare_local("sys", [])
    assert local._engine.calls == [("start", True), "read", "stop"]


def test_a_saved_local_prompt_is_left_alone(monkeypatch):
    p, local, _ = _provider(monkeypatch)
    local._engine = _Engine(saved=True)
    monkeypatch.setattr(fast, "PREPARE_AFTER", 0)
    p._prepare_local("sys", [])
    assert local._engine.calls == []


def test_the_engine_knows_what_it_saved_without_starting(tmp_path, monkeypatch):
    from brain import engine as eng
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "llama-server.exe").write_bytes(b"exe")
    monkeypatch.setattr(eng, "_ollama_lib", lambda: lib)
    monkeypatch.setattr(eng, "model_blob", lambda model: (tmp_path / "blob", "sha256:abc"))
    e = eng.LocalEngine("qwen3.5:9b", 16384, tmp_path / "state")
    e.state_dir.mkdir()
    assert not e.has_prefix("sys", [{"t": 1}])
    (e.state_dir / "prefix-x.bin").write_bytes(b"state")
    e._remember_prefix("sys", [{"t": 1}], "prefix-x.bin")
    assert e.has_prefix("sys", [{"t": 1}])
    assert not e.has_prefix("sys", [{"t": 2}]), "another prompt (coding switched on) isn't saved"


# ── connecting ───────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        return self._body


@pytest.fixture
def cloudflare_api(monkeypatch):
    """Cloudflare's token and accounts endpoints, stood in for."""
    seen = {"posts": []}

    def post(url, data=None, timeout=None, **_):
        seen["posts"].append((url, dict(data or {})))
        if url == cloudflare.TOKEN_URL and seen.get("refuse"):
            return _Resp(400, {"error": "invalid_grant"})
        n = len(seen["posts"])
        return _Resp(200, {"access_token": f"access-{n}", "refresh_token": f"refresh-{n}",
                           "expires_in": 3600})

    def get(url, headers=None, params=None, timeout=None, **_):
        seen["auth"] = headers.get("Authorization")
        return _Resp(200, {"result": [{"id": "acct123", "name": "Student's Account"}]})

    monkeypatch.setattr(cloudflare.requests, "post", post)
    monkeypatch.setattr(cloudflare.requests, "get", get)
    monkeypatch.setattr(cloudflare.requests, "head", lambda *a, **k: _Resp(200, {}))
    yield seen
    cloudflare._file().unlink(missing_ok=True)


def _browser(query: str, pages: list | None = None):
    """The browser, after Cloudflare's page: follows the redirect to Mike."""
    def open_browser(url):
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q["code_challenge_method"] == "S256" and "offline_access" in q["scope"]
        target = f"{q['redirect_uri']}?{query}&state={q['state']}"

        def follow():
            body = urllib.request.urlopen(target, timeout=5).read().decode("utf-8")
            if pages is not None:
                pages.append(body)
        threading.Thread(target=follow).start()
    return open_browser


def test_connecting_exchanges_the_code_and_finds_the_account(cloudflare_api):
    pages = []
    info = cloudflare.connect(open_browser=_browser("code=the-code", pages), timeout=10)
    for _ in range(100):             # the browser finishes reading on its own thread
        if pages:
            break
        time.sleep(0.02)
    assert "Fast mode is on." in pages[0], "the tab says what just happened"
    assert info == {"account_id": "acct123", "account_name": "Student's Account"}
    _, fields = cloudflare_api["posts"][0]
    assert fields["grant_type"] == "authorization_code" and fields["code"] == "the-code"
    assert fields["code_verifier"] and "client_secret" not in fields
    assert cloudflare_api["auth"] == "Bearer access-1"
    assert cloudflare.connected() and cloudflare.account_id() == "acct123"
    assert b"access-1" not in cloudflare._file().read_bytes()     # stored sealed


def test_an_expiring_token_is_renewed_and_the_new_refresh_token_kept(cloudflare_api):
    cloudflare._save({"access_token": "old", "refresh_token": "r0", "expires_at": time.time(),
                      "account_id": "acct123"})
    assert cloudflare.access_token().startswith("access-")
    assert cloudflare_api["posts"][-1][1]["grant_type"] == "refresh_token"
    assert cloudflare.connection()["refresh_token"].startswith("refresh-")


def test_a_revoked_connection_is_forgotten(cloudflare_api):
    cloudflare._save({"access_token": "old", "refresh_token": "r0", "expires_at": 0,
                      "account_id": "acct123"})
    cloudflare_api["refuse"] = True
    assert cloudflare.access_token() is None and not cloudflare.connected()


def test_a_declined_authorisation_says_so():
    with pytest.raises(cloudflare.CloudflareError, match="declined"):
        cloudflare.connect(open_browser=_browser(
            "error=access_denied&error_description=User+declined"), timeout=10)


# ── settings that must persist ───────────────────────────────────────────

def test_switching_coding_and_fast_mode_is_saved():
    from config import preferences
    preferences.set_value("abilities_on", "coding")
    preferences.set_value("fast_mode", False)
    try:
        assert preferences.get("abilities_on") == "coding"
        assert preferences.get("fast_mode") is False
    finally:
        preferences.set_value("abilities_on", "")
        preferences.set_value("fast_mode", True)
