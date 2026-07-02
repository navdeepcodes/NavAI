import customtkinter as ctk


class ChatBox(ctk.CTkTextbox):

    def __init__(self, master):

        super().__init__(master)

        self.insert(
            "end",
            "🤖 Mike\n\nHello Navdeep!\n\n"
        )

        self.configure(
            state="disabled"
        )

    def add_message(
        self,
        sender,
        message
    ):

        self.configure(state="normal")

        self.insert(
            "end",
            f"{sender}: {message}\n\n"
        )

        self.see("end")

        self.configure(state="disabled")