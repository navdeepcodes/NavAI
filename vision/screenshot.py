import tempfile
import subprocess


class Screenshot:

    def capture(self):

        path = tempfile.mktemp(
            suffix=".png"
        )

        subprocess.run(

            [

                "screencapture",

                "-x",

                path

            ],

            check=True

        )

        return path