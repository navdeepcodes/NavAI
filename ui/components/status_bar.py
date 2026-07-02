import customtkinter as ctk


class StatusBar(ctk.CTkFrame):

    def __init__(self, master):

        super().__init__(master)

        self.label = ctk.CTkLabel(

            self,

            text="Ready"

        )

        self.label.pack(
            padx=10,
            pady=5,
            anchor="w"
        )

    def set_status(
        self,
        text
    ):

        self.label.configure(
            text=text
        )