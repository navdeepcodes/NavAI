import customtkinter as ctk

from ui.themes.colors import *


class Message(ctk.CTkFrame):

    def __init__(
        self,
        master,
        sender,
        message,
        user=False
    ):

        super().__init__(

            master,

            fg_color=CARD,

            corner_radius=14,

            border_width=1,

            border_color=BORDER

        )

        self.pack(

            fill="x",

            padx=18,

            pady=8

        )

        title = ctk.CTkLabel(

            self,

            text=sender,

            font=(

                "SF Pro Display",

                14,

                "bold"

            ),

            text_color=TEXT

        )

        title.pack(

            anchor="w",

            padx=18,

            pady=(14,4)

        )

        body = ctk.CTkLabel(

            self,

            text=message,

            justify="left",

            wraplength=720,

            anchor="w",

            font=(

                "SF Pro Display",

                15

            ),

            text_color=TEXT

        )

        body.pack(

            fill="x",

            padx=18,

            pady=(0,16)

        )