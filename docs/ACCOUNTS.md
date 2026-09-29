# Mike accounts — setting up Supabase

Mike accounts are optional and hold only **email, name and photo**. Chats,
memory, files and activity never leave the user's computer. Until the two
values in step 5 are set, every account surface is hidden and Mike behaves
exactly as before.

What's in the repo:

| Path | What it is |
|---|---|
| `supabase/migrations/20260925000000_mike_accounts.sql` | The whole backend: `profiles` table, row-level security, sign-up trigger, private `avatars` bucket and its policies, `delete_account()` |
| `supabase/templates/*.html` | Email templates that send **6-digit codes** (Mike confirms by code, not by link) |
| `account/` | The app side: Supabase client, encrypted session store, account manager, Google sign-in |
| `tests/supabase_stack.py`, `tests/test_account_e2e.py` | A real local Supabase in Docker and end-to-end tests of every flow |

## 1. Create the project

[supabase.com](https://supabase.com) → **New project**. Pick the region
closest to your users (for India: **Mumbai, ap-south-1**).

## 2. Create the backend

**SQL Editor** → paste the contents of
`supabase/migrations/20260925000000_mike_accounts.sql` → **Run**.
(Or, with the Supabase CLI: `supabase link --project-ref <ref>` then
`supabase db push`.) It's safe to run again.

## 3. Authentication settings

**Authentication → Sign In / Providers → Email**

- Email provider: **on**. Confirm email: **on**.
- Secure email change: **on** (the default — a change is confirmed from both
  the old and the new address; Mike asks for both codes).
- Minimum password length: **8** (Mike checks the same).
- Leaked password protection: on, if your plan has it (Mike explains the
  error if a breached password is chosen).
- Email OTP length: **6**. Expiry: **3600** seconds.

**Authentication → Emails → Templates** — for each template, paste the file
and set the subject:

| Template | File | Subject |
|---|---|---|
| Confirm signup | `confirmation.html` | Your Mike code |
| Magic link | `magic_link.html` | Your Mike sign-in code |
| Change email address | `email_change.html` | Confirm your new email for Mike |
| Reset password | `recovery.html` | Reset your Mike password |
| Reauthentication | `reauthentication.html` | Confirm it's you |

**Authentication → Emails → SMTP settings** — **required before launch.**
Supabase's built-in sender only delivers to your own team's addresses and
allows a handful of emails an hour; everyone else gets "can't send email to
that address". Connect a real sender (Resend, Postmark, Amazon SES, Brevo…)
and use an address on your domain (e.g. `no-reply@huddlecode.com`).

**Authentication → Rate limits** — raise "emails sent per hour" to suit
your sign-up volume once custom SMTP is on.

**Authentication → URL Configuration**

- Site URL: your website (e.g. `https://huddlecode.com`).
- Redirect URLs: add `http://127.0.0.1:*/auth/callback` (for Google
  sign-in from the desktop app). If you'd rather list exact ports:
  `http://127.0.0.1:53682/auth/callback`, `…:53683/…`, `…:53684/…`.

## 4. Google sign-in (optional)

1. Google Cloud Console → APIs & Services → Credentials → **Create OAuth
   client ID** → *Web application*. Authorized redirect URI:
   `https://<project-ref>.supabase.co/auth/v1/callback`.
2. Supabase → **Authentication → Sign In / Providers → Google**: turn on,
   paste the client ID and secret.
3. In `config/settings.py`, set `SUPABASE_OAUTH_PROVIDERS = ["google"]` (or
   the env var `MIKE_SUPABASE_OAUTH=google`). The "Continue with Google"
   button only appears when this is set.

Mike opens Google in the user's browser and receives the result on
`127.0.0.1` with PKCE — passwords never pass through Mike.

## 5. Point Mike at the project

**Project Settings → API**: copy the **Project URL** and the **anon** (or
**publishable**) key. In `config/settings.py`:

```python
SUPABASE_URL = os.getenv("MIKE_SUPABASE_URL", "https://<project-ref>.supabase.co")
SUPABASE_ANON_KEY = os.getenv("MIKE_SUPABASE_ANON_KEY", "<anon or publishable key>")
```

Both are safe to ship inside the app — the key only identifies the project;
row-level security decides what anyone can do. **Never** put the
`service_role` / secret key in the app.

Optional: `ACCOUNT_REQUIRED = True` makes Mike usable only when signed in
(the sign-in card replaces the app until then). By default an account is
optional: offered once after the first-run tour, always available in
**Settings → Account**.

## 6. Before you launch

- Custom SMTP is on (step 3) and a test sign-up from a non-team address
  receives its code.
- Google sign-in works end to end from the installed app, if you enabled it.
- The Privacy Policy (`docs/legal/PRIVACY.md`) matches your setup — it
  names Supabase as the account provider and lists exactly email, name and
  photo. If you store anything else, update it and bump `LEGAL_VERSION`.
- Sign Supabase's DPA (Project Settings → Legal) if you have users in the
  EU/UK.

## Testing locally

With Docker running:

```sh
python -m tests.supabase_stack up      # a real Supabase on http://127.0.0.1:54321
pytest tests/test_account_e2e.py       # every flow, against it
python -m tests.supabase_stack down
```

To run the app against it, set `MIKE_SUPABASE_URL=http://127.0.0.1:54321`
and `MIKE_SUPABASE_ANON_KEY` to the key `up` prints. Codes arrive in Mailpit
at `http://127.0.0.1:54325`.

## How it behaves

- **Staying signed in.** The session is kept encrypted with Windows DPAPI
  (only the same Windows user can read it) and refreshed before it expires.
  Offline, Mike stays signed in and shows the cached name and photo.
- **Signing out** revokes the session on the server, not just locally.
- **Revoked elsewhere** (password reset, "sign out everywhere", account
  deleted): Mike signs out and says so.
- **One name.** The account's name is the name Mike calls you; an account
  without one takes the name you'd already given Mike. "About you" notes stay
  on the computer.
- **Deleting the account** (Settings → Account) removes the photo, then the
  auth user — which cascades to the profile and sessions. Local data is
  untouched.
- **Reset Mike** (Settings → Privacy) signs out and erases the local
  sign-in, but doesn't delete the account.
