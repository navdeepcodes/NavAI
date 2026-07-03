from vision.screenshot import Screenshot
from vision.analyzer import VisionAnalyzer


class Vision:

    def __init__(self):

        self.screen = Screenshot()

        self.analyzer = VisionAnalyzer()

    # -----------------------------------------
    # Capture Screenshot
    # -----------------------------------------

    def capture(self):

        return self.screen.capture()

    # -----------------------------------------
    # Analyze Existing Image
    # -----------------------------------------

    def analyze(
        self,
        image_path,
        prompt="Describe this image."
    ):

        return self.analyzer.analyze(

            image_path,

            prompt

        )

    # -----------------------------------------
    # Capture + Analyze Screen
    # -----------------------------------------

    def describe_screen(
        self,
        prompt="Describe everything visible on my screen."
    ):

        image = self.capture()

        return self.analyze(

            image,

            prompt

        )