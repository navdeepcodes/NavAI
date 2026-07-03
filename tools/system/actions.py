from __future__ import annotations

import platform
import subprocess


# ---------------------------------------------------------
# Lock Screen
# ---------------------------------------------------------

def lock() -> str:

    system = platform.system()

    if system == "Darwin":

        subprocess.run(

            [
                "pmset",
                "displaysleepnow"
            ],

            check=True

        )

    elif system == "Windows":

        subprocess.run(

            [
                "rundll32.exe",
                "user32.dll,LockWorkStation"
            ],

            check=True

        )

    else:

        raise NotImplementedError(
            "Lock not supported on this OS."
        )

    return "Screen locked."


# ---------------------------------------------------------
# Sleep
# ---------------------------------------------------------

def sleep() -> str:

    system = platform.system()

    if system == "Darwin":

        subprocess.run(

            [
                "pmset",
                "sleepnow"
            ],

            check=True

        )

    elif system == "Windows":

        raise NotImplementedError(
            "Sleep not implemented for Windows."
        )

    else:

        raise NotImplementedError(
            "Sleep not supported."
        )

    return "Computer sleeping."


# ---------------------------------------------------------
# Shutdown
# ---------------------------------------------------------

def shutdown() -> str:

    system = platform.system()

    if system == "Darwin":

        subprocess.run(

            [
                "sudo",
                "shutdown",
                "-h",
                "now"
            ],

            check=True

        )

    elif system == "Windows":

        subprocess.run(

            [
                "shutdown",
                "/s",
                "/t",
                "0"
            ],

            check=True

        )

    else:

        raise NotImplementedError()

    return "Shutdown initiated."


# ---------------------------------------------------------
# Restart
# ---------------------------------------------------------

def restart() -> str:

    system = platform.system()

    if system == "Darwin":

        subprocess.run(

            [
                "sudo",
                "shutdown",
                "-r",
                "now"
            ],

            check=True

        )

    elif system == "Windows":

        subprocess.run(

            [
                "shutdown",
                "/r",
                "/t",
                "0"
            ],

            check=True

        )

    else:

        raise NotImplementedError()

    return "Restart initiated."