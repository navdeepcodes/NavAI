from vision.screenshot import Screenshot
from vision.analyzer import VisionAnalyzer


class Vision:
    """Capture and interpret the screen.

    Two paths, deliberately: a prose description for a person asking what is
    on their screen, and a control list for the runtime deciding what to click
    next. They differ in generation budget more than anything else, and that
    budget is what vision latency is made of -- measured at a flat ~16 tokens
    per second on this machine, so the prose path costs ~10s and the control
    path ~3s.
    """

    def __init__(self):
        self.screen = Screenshot()
        self.analyzer = VisionAnalyzer()

    def capture(self):
        return self.screen.capture()

    def analyze(self, image_path, prompt="Describe this image.", max_tokens=None):
        return self.analyzer.analyze(image_path, prompt, max_tokens)

    def describe_screen(self, prompt=None, max_tokens=None):
        """Prose description, for a person reading the answer."""
        from config.ollama import VISION_NUM_PREDICT

        image = self.capture()
        return self.analyze(
            image,
            prompt or "Describe everything visible on my screen.",
            max_tokens or VISION_NUM_PREDICT,
        )

    def read_controls(self):
        """A control list rather than a description.

        Vision is the fallback for surfaces the accessibility tree cannot
        describe, and what the runtime needs there is "what can I act on",
        not prose. Asking for that directly is both more useful and about
        three times faster, because the prose prompt spends most of its
        budget on preamble.
        """
        from config.ollama import VISION_UI_NUM_PREDICT, VISION_UI_PROMPT

        image = self.capture()
        return self.analyze(image, VISION_UI_PROMPT, VISION_UI_NUM_PREDICT)
