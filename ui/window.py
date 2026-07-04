import customtkinter as ctk

from ui.themes import theme

from ui.components.header import Header
from ui.components.chat_box import ChatBox
from ui.components.input_box import InputBox

from brain.runtime import Runtime


class MikeWindow(ctk.CTk):

    def __init__(self):

        super().__init__()

        self.title("Mike")

        self.geometry("1180x760")

        self.minsize(1000, 700)

        self.configure(
            fg_color="#090B10"
        )

        self.runtime = Runtime()

        # ---------------------------------
        # Header
        # ---------------------------------

        self.header = Header(self)

        self.header.pack(
            fill="x"
        )

        # ---------------------------------
        # Chat
        # ---------------------------------

        self.chat = ChatBox(self)

        self.chat.pack(
            fill="both",
            expand=True
        )

        # ---------------------------------
        # Input
        # ---------------------------------

        self.input = InputBox(
            self,
            self.send_message
        )

        self.input.pack(
            fill="x"
        )

    # -------------------------------------

    def send_message(
        self,
        message
    ):

        self.chat.add_message(
            "You",
            message
        )

        self.header.set_activity(
            "Thinking..."
        )

        self.update()

        try:

            response = self.runtime.process(
                message
            )

            self.chat.add_message(
                "Mike",
                response.text
            )

            self.header.set_activity(
                "Ready"
            )

        except Exception as e:

            self.chat.add_message(
                "System",
                str(e)
            )

            self.header.set_activity(
                "Error"
            )