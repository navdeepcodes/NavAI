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


def create_file(path: str):
    """
    Create a file.

    Args:
        path: File path.
    """

    file = manager.create_file(path)

    return f"File created successfully at {file}."


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

    return f"Written successfully to {path}."


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

    return f"Appended text to {path}."


def list_directory(path: str):
    """
    List directory contents.

    Args:
        path: Folder path.
    """

    return manager.list_directory(path)


def delete(path: str):
    """
    Delete a file or folder.

    Args:
        path: Target path.
    """

    manager.delete(path)

    return f"{path} deleted."


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

    return f"Renamed successfully to {new_path}."


def move(
    source: str,
    destination: str
):
    """
    Move a file or folder.

    Args:
        source: Existing path.
        destination: Destination folder.
    """

    manager.move(
        source,
        destination
    )

    return f"Moved successfully."


def copy(
    source: str,
    destination: str
):
    """
    Copy a file or folder.

    Args:
        source: Existing path.
        destination: Destination folder.
    """

    manager.copy(
        source,
        destination
    )

    return f"Copied successfully."


def open_path(path: str):
    """
    Open a file or folder.

    Args:
        path: Path to open.
    """

    manager.open(path)

    return f"Opened {path}."