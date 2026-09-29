"""Mike accounts, on Supabase — optional, and only ever about who you are.

An account holds your email, the name Mike calls you and your photo, so they
follow you to any computer you use Mike on. Conversations, files, memory and
activity never go to it: they stay on the computer, account or not.

    config        where the Supabase project is, and whether accounts are on
    client        the Supabase Auth, REST and Storage calls, as plain HTTP
    session_store the signed-in session on disk, encrypted with Windows DPAPI
    manager       the app-facing account state (Qt), refresh and profile sync
    loopback      signing in with Google in the browser (PKCE, 127.0.0.1)
"""
