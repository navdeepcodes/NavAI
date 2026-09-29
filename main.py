"""Mike's entry point.

Two ways in, decided by where this executable is sitting:

  * from the folder a user just unzipped -> show the installer, because at
    that moment Mike is not installed, he is a folder in Downloads. Running
    from there leaves no Start Menu entry, nothing to double-click tomorrow,
    and breaks the moment the user tidies up their Downloads.
  * from the install location (or from source) -> just be Mike.

This lives here rather than in ui/app.py so the decision is visible at the
front door, and so the installer never has to import the whole application
to decide whether to run.
"""
import sys


def _should_offer_install() -> bool:
    """Only for a frozen build sitting outside its install location."""
    if not getattr(sys, "frozen", False):
        return False
    if "--install" in sys.argv:
        return True
    if "--no-install" in sys.argv:
        return False
    try:
        from installer import core as installer_ui
        return not installer_ui.running_from_install_dir()
    except Exception:
        # Never let the installer check stop Mike from starting.
        return False


if __name__ == "__main__":
    if "--uninstall" in sys.argv:
        from installer import core as installer_ui
        installer_ui.uninstall()
        sys.exit(0)

    if _should_offer_install():
        from installer.window import run_installer
        sys.exit(run_installer())

    from ui.app import run
    run()
