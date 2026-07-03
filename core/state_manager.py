from memory.working_memory import WorkingMemory


class StateManager:

    def __init__(self):

        self.memory = WorkingMemory()

    # --------------------------

    def topic(self):

        return self.memory.get(
            "current_topic"
        )

    def set_topic(
        self,
        topic
    ):

        self.memory.update(
            "current_topic",
            topic
        )

    # --------------------------

    def task(self):

        return self.memory.get(
            "active_task"
        )

    def set_task(
        self,
        task
    ):

        self.memory.update(
            "active_task",
            task
        )

    # --------------------------

    def project(self):

        return self.memory.get(
            "active_project"
        )

    def set_project(
        self,
        project
    ):

        self.memory.update(
            "active_project",
            project
        )

    # --------------------------

    def tool(self):

        return self.memory.get(
            "last_tool"
        )

    def set_tool(
        self,
        tool
    ):

        self.memory.update(
            "last_tool",
            tool
        )

    # --------------------------

    def clear(self):

        self.memory.clear()