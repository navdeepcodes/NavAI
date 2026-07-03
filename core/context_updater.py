class ContextUpdater:

    def update(

        self,

        state,

        message

    ):

        text = message.lower()

        if "project" in text:

            state.set_topic(

                "Project"

            )

        if "calendar" in text:

            state.set_topic(

                "Calendar"

            )

        if "memory" in text:

            state.set_topic(

                "Memory"

            )

        if "browser" in text:

            state.set_topic(

                "Browser"

            )

        if "email" in text:

            state.set_topic(

                "Email"

            )