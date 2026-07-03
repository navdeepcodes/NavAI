class TaskQueue:

    def __init__(self):

        self.tasks = []

    def add(self, task):

        self.tasks.append(task)

    def next(self):

        for task in self.tasks:

            if not task.completed:

                return task

        return None

    def completed(self):

        return all(
            task.completed
            for task in self.tasks
        )

    def clear(self):

        self.tasks.clear()