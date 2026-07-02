from logs.logger import logger

from voice.microphone import initialize_microphone
from voice.recorder import Recorder
from voice.player import Player

from brain.assistant import initialize_brain
from brain.brain import Brain

from tools.manager import ToolManager


class Mike:

    def __init__(self):
        logger.info("Creating Mike...")

        self.tool_manager = None
        self.brain = Brain()

        self.recorder = Recorder()
        self.player = Player()

    def startup(self):
        logger.info("Starting subsystems...")

        initialize_microphone()
        initialize_brain()

        self.tool_manager = ToolManager()

        logger.info("Mike is ready.")

    def run(self):

        self.startup()

        while True:

            user_input = input("\nYou: ").strip()

            if user_input.lower() == "exit":

                logger.info("Mike shutting down.")
                print("👋 Goodbye!")
                break

            try:

                action = self.brain.think(user_input)

                if action.is_tool:

                    success = self.tool_manager.execute(
                        action.tool,
                        action.action,
                        **action.parameters
                    )

                    if success:

                        print(f"\n🤖 Mike: {action.response}")

                    else:

                        print("\n🤖 Mike: Sorry, I couldn't complete that action.")

                else:

                    print(f"\n🤖 Mike: {action.response}")

            except Exception as e:

                logger.exception(e)

                print("\n❌ Mike encountered an internal error.")