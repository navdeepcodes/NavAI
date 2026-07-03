from pathlib import Path
import shutil
import subprocess

from tools.filesystem.path_utils import resolve_path


class FileManager:

    # -----------------------------
    # Folder Operations
    # -----------------------------

    def create_folder(self, path: str):

        folder = resolve_path(path)

        folder.mkdir(
            parents=True,
            exist_ok=True
        )

        return str(folder)


    def list_directory(self, path: str):

        folder = resolve_path(path)

        return [
            item.name
            for item in folder.iterdir()
        ]


    # -----------------------------
    # File Operations
    # -----------------------------

    def create_file(self, path: str):

        file = resolve_path(path)

        file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        file.touch(exist_ok=True)

        return str(file)


    def read_file(self, path: str):

        file = resolve_path(path)

        return file.read_text(
            encoding="utf-8"
        )


    def write_file(
        self,
        path: str,
        content: str
    ):

        file = resolve_path(path)

        file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        file.write_text(
            content,
            encoding="utf-8"
        )

        return str(file)


    def append_file(
        self,
        path: str,
        content: str
    ):

        file = resolve_path(path)

        with open(
            file,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(content)

        return str(file)


    # -----------------------------
    # Universal
    # -----------------------------

    def delete(self, path: str):

        target = resolve_path(path)

        if target.is_dir():

            shutil.rmtree(target)

        else:

            target.unlink()

        return True


    def rename(
        self,
        source: str,
        new_name: str
    ):

        src = resolve_path(source)

        dst = src.parent / new_name

        src.rename(dst)

        return str(dst)


    def move(
        self,
        source: str,
        destination: str
    ):

        src = resolve_path(source)

        dst = resolve_path(destination)

        shutil.move(
            str(src),
            str(dst)
        )

        return str(dst)


    def copy(
        self,
        source: str,
        destination: str
    ):

        src = resolve_path(source)

        dst = resolve_path(destination)

        if src.is_dir():

            shutil.copytree(
                src,
                dst,
                dirs_exist_ok=True
            )

        else:

            shutil.copy2(
                src,
                dst
            )

        return str(dst)


    def open(self, path: str):

        target = resolve_path(path)

        subprocess.run(
            ["open", str(target)]
        )

        return True