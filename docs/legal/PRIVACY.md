# Privacy Policy

**Last updated: {updated}** · Mike {version} · Published by {publisher}

Mike is an assistant that runs on your computer. This policy explains, in plain
language, what Mike keeps, where it keeps it, and the few times it uses the
internet. It is written to match what the app actually does.

## The short version

- **Mike thinks on your computer.** In its standard setup, your conversations,
  files, screen and voice are processed by software running on your own
  machine — not on our servers.
- **We don't collect your data.** There are no analytics, no telemetry, no
  advertising, and no automatic crash reporting. {publisher} does not receive
  your conversations, files, voice or usage.
- **An account is optional, and only about who you are.** If you create a
  Mike account, it holds your email, your name and, if you add one, your
  photo — never your conversations, memory, files or activity.
- **Mike uses the internet only for specific things you'll recognise** —
  downloading its models, searches and websites you ask for, your account if
  you sign in, and email if you connect Gmail. Each is listed below.
- **You're in control.** You can see, export and delete everything Mike keeps,
  and turn off any ability in **Settings → Permissions**.

## What Mike keeps on your computer

Mike stores the following in its data folder on your computer
(`{data_dir}`), protected by your Windows user account:

| What | Why | How to remove it |
|---|---|---|
| **Chats** — what you and Mike said | So you can reopen and continue them | Delete a chat from the sidebar, or **Settings → Privacy → Delete all chats** |
| **Memory** — facts you asked Mike to remember | So Mike can use them later | **Settings → Memory**, or **Forget all** |
| **Activity** — what Mike did (files written, apps opened, commands run) | So you can always see what Mike did | **Settings → Privacy → Clear activity history** |
| **Preferences** — your name, theme, voice and other settings | To remember your choices | **Settings → Privacy → Reset Mike** |
| **Logs** — technical records of what Mike did, which can include parts of your requests, file names and commands | To diagnose problems | Kept to a few MB and replaced automatically; erased by **Reset Mike** |
| **Your last voice recording** — a temporary file of the last thing you said by voice | To turn your speech into text | Overwritten by the next recording; erased by **Reset Mike** |
| **Your sign-in, if you have an account** — a session token, and a copy of your name, email and photo so Mike can show them offline | To keep you signed in | **Settings → Account → Sign out**, or **Reset Mike**. On Windows the session is encrypted so only your Windows user can read it |

Files you attach to a message stay where they are; Mike reads them but keeps
only their name in the chat.

## Microphone, screen and your computer

- **Microphone.** Mike listens when you press the mic button or F6, and stops
  when you pause. If you turn on **"Hey Mike"**, Mike listens continuously for
  that phrase — the listening and recognition happen entirely on your
  computer, and nothing is recorded or sent anywhere while it waits.
- **Screen.** Mike looks at your screen only when you ask it to (for example,
  "what's on my screen?") or when a task you asked for needs it. The image is
  analysed on your computer.
- **Using your apps and files.** When you ask, Mike can open apps, click, type,
  and read or change files. Anything that can't be quietly undone — deleting,
  overwriting, sending — is shown to you first and only happens if you
  approve. You can turn any of these abilities off in **Settings →
  Permissions**.

## When Mike uses the internet

Mike connects to the internet only in these situations:

1. **Downloading its brain and voice.** The first time it's needed, Ollama
   downloads Mike's language model from Ollama's model library, and Mike
   downloads its speech-recognition model from Hugging Face. As with any
   download, those services see your IP address and which model was requested.
   Your conversations are not sent.
2. **Searches and websites you ask for.** When you ask Mike to search the web,
   your search words are sent to the search provider (Microsoft Bing, and Google
   News for news) to fetch results. Websites Mike opens for you load in your
   browser as normal. Those services' own privacy policies apply. You can turn
   this off in **Settings → Permissions → Use the web**.
3. **Gmail, only if you connect it.** If you connect your Google account, Mike
   uses Google's Gmail service to send email you've approved and to read your
   inbox when you ask. Mike asks Google only for permission to read and send
   email. The sign-in token is stored on your computer. You can disconnect
   Mike at any time from your Google Account's security settings. Google's
   privacy policy applies to data sent to Google.
4. **Your Mike account, if you have one.** While you're signed in, Mike
   contacts our account service (run on Supabase) to keep you signed in and to
   sync your name and photo. Nothing else is sent. See "Your Mike account"
   below.
5. **Checks you ask for.** Developer tools such as "check this URL" contact the
   address you give.

**Cloud AI is not used in the standard setup.** Mike ships configured to use a
model running on your own computer. The software can be reconfigured by a
developer to use an online AI service instead; if it is, your conversations are
sent to that service under its terms.

## Your Mike account (optional)

You can use every part of Mike without an account. If you create one
(**Settings → Account**), this is what it involves:

- **What it holds:** your email address, your password (stored only as a
  secure hash — nobody, including us, can read it), the name Mike calls you,
  and your photo if you add one. If you sign in with Google, Google shares
  your name, email address and profile picture link with us.
- **What it never holds:** your conversations, memory, files, activity,
  "about you" notes, voice or screen. These stay on your computer whether or
  not you're signed in.
- **Who stores it:** accounts are run on Supabase (supabase.com), which
  stores the account on our behalf and processes it only to provide the
  service. Like most online services, it keeps short-lived security logs of
  sign-ins, including IP addresses, to prevent abuse.
- **Emails:** we email you only to confirm your address, send sign-in and
  password-reset codes, and confirm an email change — never marketing.
- **Who can see it:** only you. Each account can read and change only its
  own profile and photo; your photo is not public.
- **Deleting it:** **Settings → Account → Delete account** permanently
  deletes your account, profile and photo straight away. Signing out removes
  your sign-in from this computer and ends that session.

## What we collect

Nothing, automatically. {publisher} has no servers that receive your
conversations or usage from Mike. The only information we hold about you is
your Mike account, if you choose to create one (see above).

If you choose **Settings → About → Report a problem**, Mike creates a file on
your computer containing technical information (version, system details,
settings, and Mike's logs, which can include parts of your requests). You can
look inside it before deciding whether to send it to us. We use a report you
send only to fix the problem you reported, and delete it when we're done.

## Your choices

- **See and delete:** chats (sidebar), memory, and activity (Settings).
- **Your account:** change your name, photo, email or password, sign out, or
  delete the account in **Settings → Account**.
- **Export:** **Settings → Privacy → Export my data** saves everything Mike
  keeps as readable files.
- **Erase everything:** **Settings → Privacy → Reset Mike**.
- **Limit what Mike can do:** **Settings → Permissions**.
- **Uninstall:** removing Mike removes the app; you can also delete its data
  folder shown above.

## Children

Mike is intended for people aged 13 and over. People under 18 should use Mike
with the permission of a parent or guardian.

## Changes to this policy

If we change this policy in a way that matters, Mike will show you the new
version and ask you to accept it before you continue.

## Contact

Questions about privacy: {contact}
