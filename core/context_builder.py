from memory.working_memory import WorkingMemory


class ContextBuilder:

    def __init__(self):

        self.working = WorkingMemory()

    def build(

        self,

        system_prompt,

        long_term,

        history

    ):

        messages = []

        messages.append({

            "role": "system",

            "content": system_prompt

        })

        working = self.working.all()

        if working:

            text = ""

            for key, value in working.items():

                text += f"{key}: {value}\n"

            messages.append({

                "role": "system",

                "content":

                "Working Memory\n\n"

                + text

            })

        if long_term:

            messages.append({

                "role": "system",

                "content":

                "Long Term Memory\n\n"

                + long_term

            })

        messages.extend(history)

        return messages