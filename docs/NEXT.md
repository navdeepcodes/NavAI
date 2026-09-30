# Next up (handover, 30 Sep 2026)

State: Mike 1.1.0 is public (GitHub release v1.1.0, huddlecode.com). The
Windows laptop used so far is gone; Windows builds now come from GitHub
Actions (`windows-build.yml`, see docs/RELEASING.md). Everything is pushed.

## 1.1.1 — already on `main`, not yet released
- Mike knows who built him ("Navdeep and the team at Huddle Labs").

## 1.1.1 — to build: ask for permissions on a fresh install
The first-run tour (ui/welcome.py) explains Mike, then asks only for the
Terms/Privacy agreement. Add one card before consent that asks for:
- **Microphone.** Windows never prompts desktop apps: if Settings → Privacy →
  Microphone → "Let desktop apps access your microphone" is off, voice is
  silently dead. Read HKCU\Software\Microsoft\Windows\CurrentVersion\
  CapabilityAccessManager\ConsentStore\microphone (Value, and NonPackaged\Value);
  if "Deny", say so and offer a button that opens `ms-settings:privacy-microphone`.
- **Mike's abilities** (brain/permissions.py ABILITIES: apps, screen, files,
  commands, documents, coding, web, email, memory): a switch each, all on,
  one line each; save through the same preference Settings → Permissions uses.
- **Start at sign-in** (hostplatform/autostart) and **notifications**
  (preference `notifications_enabled`): ask, don't set silently.
- Screen reading and clicking need no Windows permission — don't invent one.

Test on a Mac first (the tour is plain Qt: `QT_QPA_PLATFORM=offscreen`
pytest), then build with `gh workflow run windows-build.yml` (no tag) and try
the artifact on any Windows PC before `gh release create v1.1.1`.

## Never tested yet
- A clean Windows PC that never had Mike (install, Ollama, first chat).
- Voice feel in real use; the nib guide outside Notepad.
