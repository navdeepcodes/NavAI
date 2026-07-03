import customtkinter as ctk

from ui.components.message import Message

from ui.themes.colors import *


class ChatBox(ctk.CTkScrollableFrame):

    def __init__(

        self,

        master

    ):

        super().__init__(

            master,

            fg_color=BACKGROUND,

            corner_radius=0

        )

        self.messages=[]

        self.add_message(

            "Mike",

            "Hello Navdeep."

        )

    def add_message(

        self,

        sender,

        text

    ):

        msg=Message(

            self,

            sender,

            text,

            user=sender=="You"

        )

        self.messages.append(msg)

    def clear(self):

        for widget in self.winfo_children():

            widget.destroy()

        self.messages.clear()