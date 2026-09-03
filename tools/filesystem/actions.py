from tools.filesystem.file_manager import FileManager


manager = FileManager()


def create_folder(path: str):
    """
    Create a folder.

    Args:
        path: Folder path.
    """

    folder = manager.create_folder(path)

    return f"Folder created successfully at {folder}."


def create_file(path: str, content: str | None = None):
    """
    Create a file, optionally with initial content.

    Args:
        path: File path.
        content: Text to write. Omit for an empty file.
    """

    file = manager.create_file(path, content)

    if content is None:
        return f"File created successfully at {file}."

    return f"File created successfully at {file} ({len(content)} characters)."


def read_file(path: str):
    """
    Read a text file.

    Args:
        path: File path.
    """

    return manager.read_file(path)


def write_file(
    path: str,
    content: str
):
    """
    Write text to a file.

    Args:
        path: File path.
        content: Text to write.
    """

    manager.write_file(
        path,
        content
    )

    return f"Successfully wrote to {path}."


def append_file(
    path: str,
    content: str
):
    """
    Append text to a file.

    Args:
        path: File path.
        content: Text to append.
    """

    manager.append_file(
        path,
        content
    )

    return f"Successfully appended text to {path}."


def list_directory(path: str):
    """
    List files and folders inside a directory.

    Args:
        path: Directory path.
    """

    return manager.list_directory(path)


def delete(path: str):
    """
    Delete a file or folder.

    Args:
        path: Target path.
    """

    manager.delete(path)

    return f"Deleted '{path}' successfully."


def rename(
    source: str,
    new_name: str
):
    """
    Rename a file or folder.

    Args:
        source: Existing path.
        new_name: New filename.
    """

    new_path = manager.rename(
        source,
        new_name
    )

    return f"Renamed successfully to '{new_path}'."


def move(
    source: str,
    destination: str
):
    """
    Move a file or folder.

    Args:
        source: Existing path.
        destination: Destination path.
    """

    manager.move(
        source,
        destination
    )

    return f"Moved '{source}' to '{destination}'."


def copy(
    source: str,
    destination: str
):
    """
    Copy a file or folder.

    Args:
        source: Existing path.
        destination: Destination path.
    """

    manager.copy(
        source,
        destination
    )

    return f"Copied '{source}' to '{destination}'."


def open_path(path: str):
    """
    Open a file or folder in Finder.

    Args:
        path: File or folder path.
    """

    manager.open(path)

    return f"Opened '{path}'."