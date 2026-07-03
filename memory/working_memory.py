import json
from pathlib import Path


STATE_FILE = (
    Path(__file__).parent
    / "working"
    / "state.json"
)


class WorkingMemory:

    def __init__(self):

        STATE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if not STATE_FILE.exists():

            self.save({})

        else:

            try:
                self.load()

            except Exception:
                self.save({})

    # -------------------------------------

    def load(self):

        try:

            with open(
                STATE_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                return json.load(f)

        except Exception:

            return {}

    # -------------------------------------

    def save(
        self,
        data
    ):

        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

    # -------------------------------------

    def update(
        self,
        key,
        value
    ):

        data = self.load()

        data[key] = value

        self.save(data)

    # -------------------------------------

    def update_many(
        self,
        **kwargs
    ):

        data = self.load()

        data.update(kwargs)

        self.save(data)

    # -------------------------------------

    def remove(
        self,
        key
    ):

        data = self.load()

        if key in data:

            del data[key]

            self.save(data)

    # -------------------------------------

    def get(
        self,
        key,
        default=None
    ):

        return self.load().get(
            key,
            default
        )

    # -------------------------------------

    def all(self):

        return dict(
            self.load()
        )

    # -------------------------------------

    def clear(self):

        self.save({})