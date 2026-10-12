# Releasing a new version of Mike

Everyone on Mike 1.1.0 or later updates from inside the app: Mike checks
GitHub shortly after starting and twice a day, finds the newest release that
has a `Mike-windows-<version>.zip` attached, and offers it in the chat
(`installer/updates.py`, `ui/workspace/updater.py`). So shipping a fix is:
publish a release with the zip attached. It works from any computer — the
Windows build runs on GitHub's own Windows machines, so a Mac is enough.

## Ship a fix

1. **Fix it, and raise the version** in `config/settings.py`:
   `VERSION = "1.1.1"`. The number must go up — that's how installed copies
   know it's newer. If the Privacy Policy or Terms changed, also bump
   `LEGAL_VERSION` (everyone is asked to accept the new text once).
2. **Run the tests** that cover what you changed, commit, and push to `main`.
3. **Create the release** (the tag is made from `main`):

   ```sh
   gh release create v1.1.1 --title "Mike 1.1.1" --notes "What changed, in a sentence or two."
   ```

   The first line of the notes is what Mike shows in the update banner.
4. **Build and attach the Windows zip** on GitHub's Windows machine:

   ```sh
   gh workflow run windows-build.yml -f release_tag=v1.1.1
   gh run watch
   ```

   It fetches the voice runtime (`packaging/fetch_runtime.py`), builds with
   `packaging/build_windows.py`, builds the one-file installer
   (`packaging/mike.iss` → `Mike-Setup-1.1.1.exe`), and attaches both
   `Mike-windows-1.1.1.zip` and `Mike-Setup-1.1.1.exe` to the release. The zip
   is what installed copies update from; the Setup.exe is what a new person
   downloads. Until the zip is attached, installed copies simply don't see
   the release — there's no window where they'd try to download nothing.

   The same run installs the Setup.exe silently on the Windows machine, runs
   `Mike.exe --self-check` (fails the build if any tool is missing from the
   package), simulates the in-app update's folder swap, and uninstalls. A red
   run means don't release.

   **macOS** has no updater yet. Build and verify with
   `python packaging/build_macos.py <out>` (it runs the same `--self-check` on
   the built app), then `ditto -c -k --keepParent <out>/Mike.app
   Mike-macOS-1.1.1.zip`, attach it with `gh release upload`, and update the
   version and `sha256` in the Homebrew cask.
5. **Point the website at it**: in `mike-website/public/index.html`, change
   the two `releases/download/v…/Mike-windows-….zip` links and
   `softwareVersion`; if the policy changed, run
   `python3 scripts/build_legal.py ../NavAI/docs/legal`; then
   `npx wrangler deploy`.

Installed copies pick the update up within about 12 hours (or right away from
**Settings → About → Check now**).

## If a release is bad

Publish a newer version with the fix (steps 1–4 again, e.g. 1.1.2). Mike never
moves to a lower version number, so deleting a release doesn't roll anyone
back — it only stops new updates to it. For a build that must not be
installed at all, delete its zip from the release right away:
`gh release delete-asset v1.1.1 Mike-windows-1.1.1.zip`.

## Checking a build before releasing it

`gh workflow run windows-build.yml` with no `release_tag` only builds; the zip
is under the run's **Artifacts** for 30 days. On a Windows PC: unzip it, run
`Mike.exe`, install, and try the change.

To try the whole update path without publishing anything, point an installed
Mike at a stand-in list of releases with the `MIKE_UPDATE_FEED` environment
variable (a URL returning the same JSON as GitHub's
`/repos/navdeepcodes/NavAI/releases`).

## Things to know

- **Unsigned builds.** Mike isn't code-signed, so Windows SmartScreen warns
  when a *downloaded* zip is first opened (More info → Run anyway). Updates
  from inside Mike don't carry that warning. A code-signing certificate
  removes it for new downloads too.
- **1.0.0 can't update itself** — the update check arrived in 1.1.0. People
  on 1.0.0 need to download 1.1.0 once from the website; it closes the old
  Mike, replaces it, and keeps their chats and settings.
