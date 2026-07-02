import sounddevice as sd
import soundfile as sf

from logs.logger import logger


class Player:

    def play(self, filename):

        logger.info(f"Playing {filename}")

        data, samplerate = sf.read(filename)

        sd.play(data, samplerate)

        sd.wait()

        logger.info("Playback finished.")