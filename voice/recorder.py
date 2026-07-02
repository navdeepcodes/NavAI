import os
import sounddevice as sd
import soundfile as sf

from logs.logger import logger


class Recorder:

    def __init__(self):

        self.sample_rate = 44100
        self.channels = 1

        os.makedirs("audio/recordings", exist_ok=True)

    def record(self, duration=5):

        logger.info(f"Recording for {duration} seconds...")

        print("🎤 Recording...")

        recording = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32"
        )

        sd.wait()

        filename = "audio/recordings/recording.wav"

        sf.write(
            filename,
            recording,
            self.sample_rate
        )

        logger.info(f"Recording saved to {filename}")

        print("✅ Recording Complete")

        return filename