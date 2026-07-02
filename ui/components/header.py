import customtkinter as ctk

from ui.themes.colors import *


class Header(ctk.CTkFrame):

    def __init__(self, master):

        super().__init__(master)

        self.configure(height=60)

        title = ctk.CTkLabel(

            self,

            text="🤖 Mike",

            font=("SF Pro Display", 24, "bold")

        )

        title.pack(
            side="left",
            padx=20,
            pady=15
        )

        status = ctk.CTkLabel(

            self,

            text="🟢 Online",

            text_color=SUCCESS

        )

        status.pack(
            side="right",
            padx=20
        )