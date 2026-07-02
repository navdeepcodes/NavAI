import customtkinter as ctk

from ui.themes import theme

from ui.components.header import Header
from ui.components.chat_box import ChatBox
from ui.components.input_box import InputBox
from ui.components.status_bar import StatusBar

from core.runtime import Runtime


class MikeWindow(ctk.CTk):

    def __init__(self):

        super().__init__()

        self.title("Mike")

        self.geometry("900x650")

        self.minsize(700, 500)

        self.runtime = Runtime()

        self.header = Header(self)
        self.header.pack(fill="x")

        self.chat = ChatBox(self)
        self.chat.pack(fill="both", expand=True)

        self.input = InputBox(
            self,
            self.send_message
        )

        self.input.pack(fill="x")

        self.status = StatusBar(self)
        self.status.pack(fill="x")

    def send_message(self, message):

        self.chat.add_message("👤 You", message)

        self.status.set_status("Mike is thinking...")

        self.update()

        try:

            response = self.runtime.process(message)

            self.chat.add_message(
                "🤖 Mike",
                response.text
            )

            self.status.set_status("Ready")

        except Exception as e:

            self.chat.add_message(
                "❌ Error",
                str(e)
            )

            self.status.set_status("Error")