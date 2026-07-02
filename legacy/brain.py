from logs.logger import logger

from brain.processor import Processor


class Brain:

    def __init__(self):

        logger.info("Initializing Brain...")

        self.processor = Processor()

    def think(self, message):

        return self.processor.process(message)