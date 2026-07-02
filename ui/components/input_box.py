import customtkinter as ctk


class InputBox(ctk.CTkFrame):

    def __init__(self, master, send_callback):

        super().__init__(master)

        self.send_callback = send_callback

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text="Ask Mike anything..."
        )

        self.entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=10,
            pady=10
        )

        self.entry.bind(
            "<Return>",
            self.send_message
        )

        self.button = ctk.CTkButton(

            self,

            text="Send",

            command=self.send_message

        )

        self.button.pack(
            side="right",
            padx=10,
            pady=10
        )

    def send_message(self, event=None):

        message = self.entry.get().strip()

        if not message:
            return

        self.entry.delete(0, "end")

        self.send_callback(message)