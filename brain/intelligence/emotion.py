from brain.intelligence.models import Emotion


class EmotionDetector:

    def detect(
        self,
        message: str
    ) -> Emotion:

        text = message.lower()

        if any(word in text for word in [

            "sad",

            "upset",

            "depressed",

            "failed"

        ]):

            return Emotion(

                label="sad",

                confidence=0.9

            )

        if any(word in text for word in [

            "lets go",

            "woo",

            "awesome",

            "finally"

        ]):

            return Emotion(

                label="excited",

                confidence=0.9

            )

        return Emotion()