from logs.logger import logger

from voice.microphone import initialize_microphone
from voice.recorder import Recorder
from voice.player import Player

from brain.assistant import initialize_brain

from core.runtime import Runtime


class Mike:

    def __init__(self):

        logger.info("Creating Mike...")

        self.runtime = Runtime()

        self.recorder = Recorder()
        self.player = Player()

    def startup(self):

        logger.info("Starting subsystems...")

        initialize_microphone()
        initialize_brain()

        logger.info("Mike is ready.")

    def run(self):

        self.startup()

        while True:

            try:

                user_input = input("\nYou: ").strip()

                if not user_input:
                    continue

                if user_input.lower() == "exit":

                    logger.info("Mike shutting down.")

                    print("👋 Goodbye!")

                    break

                response = self.runtime.process(user_input)

                # Print Gemini's reply
                print(f"\n🤖 Mike: {response.text}")

            except KeyboardInterrupt:

                logger.info("Mike stopped by user.")

                print("\n👋 Goodbye!")

                break

            except Exception as e:

                logger.exception(e)

                print("\n❌ Mike encountered an internal error.")