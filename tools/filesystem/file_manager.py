import shutil
import subprocess

from tools.filesystem.path_utils import resolve_path

# Formats that are packages or binaries, not text. Writing text into one
# destroys it: measured, asked to "help finish" a lab report, Mike wrote the
# answer into Lab3_report.docx as plain text and the student's document no
# longer opened.
NOT_TEXT = {
    ".docx": "a Word document", ".doc": "a Word document", ".odt": "a document",
    ".pptx": "a PowerPoint deck", ".ppt": "a PowerPoint deck",
    ".xlsx": "an Excel workbook", ".xls": "an Excel workbook",
    ".pdf": "a PDF", ".zip": "an archive", ".png": "an image", ".jpg": "an image",
    ".jpeg": "an image", ".gif": "an image", ".exe": "a program",
}


def refuse_non_text(file) -> None:
    kind = NOT_TEXT.get(file.suffix.lower())
    if kind is None:
        return
    extra = (" For a workbook, use edit_spreadsheet." if "Excel" in kind else
             " Write the text in your reply for the user to paste, or type it into the "
             "open document with type_text.")
    raise ValueError(
        f"{file.name} is {kind}, not a text file — writing text into it would "
        f"break it, so nothing was written.{extra}")


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

    def create_file(self, path: str, content: str | None = None):

        file = resolve_path(path)
        if content:
            refuse_non_text(file)

        file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if content is None:
            file.touch(exist_ok=True)
        else:
            file.write_text(content)

        return str(file)


    MAX_READ_CHARS = 12_000

    #: Documents read_file hands to the document reader instead of dumping as
    #: bytes. Measured: read_file on a .docx returned 12,000 characters of zip
    #: garbage, the prompt overflowed, and the next model call ran for minutes.
    DOCUMENTS = {".docx", ".pptx", ".pdf", ".xlsx", ".xls", ".csv"}

    def read_file(self, path: str):

        file = resolve_path(path)

        if file.suffix.lower() in self.DOCUMENTS:
            from tools.filesystem.document_reader import read_document
            return read_document(str(file))

        with open(file, "rb") as probe:
            if b"\x00" in probe.read(4096):
                raise ValueError(
                    f"{file.name} is a binary file, not text, so it can't be shown "
                    "as text. For documents use read_document.")

        text = file.read_text(
            encoding="utf-8",
            errors="replace",
        )

        if len(text) > self.MAX_READ_CHARS:
            return (
                text[:self.MAX_READ_CHARS]
                + f"\n\n--- Truncated: showing first {self.MAX_READ_CHARS:,} of "
                f"{len(text):,} characters. ---"
            )

        return text


    def write_file(
        self,
        path: str,
        content: str
    ):

        file = resolve_path(path)
        refuse_non_text(file)

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
        refuse_non_text(file)

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