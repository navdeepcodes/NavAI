import customtkinter as ctk

from ui.themes.colors import *


class Header(ctk.CTkFrame):

    def __init__(self, master):

        super().__init__(

            master,

            height=58,

            fg_color=SURFACE,

            corner_radius=0

        )

        self.pack_propagate(False)

        self.title = ctk.CTkLabel(

            self,

            text="New Conversation",

            font=(

                "SF Pro Display",

                22,

                "bold"

            ),

            text_color=TEXT

        )

        self.title.pack(

            side="left",

            padx=22

        )

        self.activity = ctk.CTkLabel(

            self,

            text="Ready",

            font=(

                "SF Pro Display",

                13

            ),

            text_color=TEXT_SECONDARY

        )

        self.activity.pack(

            side="right",

            padx=20

        )

    def set_activity(

        self,

        text

    ):

        self.activity.configure(

            text=text

        )