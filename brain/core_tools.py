from __future__ import annotations

from google.genai import types


# ============================================================
# Tool Definitions for Gemini native tool calling
# ============================================================

TOOL_DECLARATIONS = [

    # --------------------------------------------------------
    # Browser
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="open_browser",
        description="Open the user's default web browser.",
    ),

    types.FunctionDeclaration(
        name="open_url",
        description=(
            "Open a specific URL in the browser. "
            "Use this for site-specific searches by constructing the search URL directly. "
            "For example, to search YouTube use 'https://www.youtube.com/results?search_query=QUERY', "
            "to search Wikipedia use 'https://en.wikipedia.org/w/index.php?search=QUERY'."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to open",
                }
            },
            "required": ["url"],
        },
    ),

    types.FunctionDeclaration(
        name="search_web",
        description=(
            "Search the web and return the top results with summaries. "
            "Use this when the user wants to know about current events, news, "
            "or any information that requires a web search. "
            "Do NOT use this for site-specific searches like 'search YouTube for X' — "
            "use open_url with the site's search URL instead."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                }
            },
            "required": ["query"],
        },
    ),

    # --------------------------------------------------------
    # Filesystem
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="create_folder",
        description=(
            "Create a new folder. "
            "Paths like 'Desktop/MyFolder' or 'Documents/project' "
            "resolve to the user's home directories automatically."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Folder path to create",
                }
            },
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="create_file",
        description=(
            "Create a file. Pass content to write it in at the same time, "
            "or omit content for an empty file. Parent folders are created "
            "automatically."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to create",
                },
                "content": {
                    "type": "string",
                    "description": "Optional text to write into the new file",
                },
            },
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="read_file",
        description="Read the contents of a text file.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to read",
                }
            },
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="write_file",
        description="Write content to a file, creating it if it does not exist. Overwrites existing content.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to write to",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write",
                },
            },
            "required": ["path", "content"],
        },
    ),

    types.FunctionDeclaration(
        name="list_directory",
        description="List files and folders inside a directory.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list",
                }
            },
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="delete_path",
        description="Delete a file or folder permanently.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to delete",
                }
            },
            "required": ["path"],
        },
    ),

    # --------------------------------------------------------
    # Terminal
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="run_command",
        description=(
            "Execute a shell command that finishes on its own and return its "
            "output. Do NOT use this for servers or anything that keeps "
            "running — it will time out. Use run_background for those."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional directory to run the command in",
                },
            },
            "required": ["command"],
        },
    ),

    types.FunctionDeclaration(
        name="run_background",
        description=(
            "Start a long-running process that should keep running — a dev "
            "server, a watcher, anything that doesn't exit on its own. "
            "Returns immediately once it's up instead of waiting for it."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to start",
                },
                "cwd": {
                    "type": "string",
                    "description": "Directory to start it in",
                },
            },
            "required": ["command"],
        },
    ),

    # --------------------------------------------------------
    # Applications
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="open_application",
        description=(
            "Open or focus an application on the user's Mac. Use this only "
            "when the user asked to open or switch to an app — not when they "
            "are asking a question about apps."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Application name as macOS knows it, e.g. "
                        "'Visual Studio Code', 'Safari', 'Terminal'"
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Only when the user named an actual file or folder to "
                        "open in that app. The app name alone is enough to "
                        "launch it — never invent a path for the app itself."
                    ),
                },
            },
            "required": ["name"],
        },
    ),

    # --------------------------------------------------------
    # Documents
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="read_document",
        description=(
            "Read and extract text from a document file. "
            "Supports PDF, DOCX, PPTX, CSV, JSON, and all text-based files. "
            "Use this instead of read_file when the user asks about a document, "
            "especially for PDF, DOCX, or PPTX files. "
            "For plain text files (.txt, .md, .py, etc.), read_file also works."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the document file",
                }
            },
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="search_files",
        description=(
            "Search for text content inside files, or find files by name. "
            "Use this when the user asks to find something in their files or code. "
            "Examples: 'find all files that mention TODO', 'find Python files on Desktop'."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for inside files, or filename pattern to find",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: current directory or Desktop)",
                },
                "file_type": {
                    "type": "string",
                    "description": "File extension filter, e.g. 'py', 'txt', 'js' (optional)",
                },
            },
            "required": ["query"],
        },
    ),

    # --------------------------------------------------------
    # Memory
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="remember",
        description=(
            "Save a useful fact the user explicitly asks you to remember. "
            "Use this ONLY when the user says things like 'remember that...', "
            "'don't forget that...', 'save this...', 'keep in mind that...'. "
            "Do NOT use this for normal conversation or tool requests."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The fact to remember, written as a clear statement",
                },
                "category": {
                    "type": "string",
                    "description": "One of: preference, person, project, location, workflow, fact",
                    "enum": ["preference", "person", "project", "location", "workflow", "fact"],
                },
            },
            "required": ["content", "category"],
        },
    ),

    types.FunctionDeclaration(
        name="recall_memory",
        description=(
            "Search your memory for previously saved facts. "
            "Use this when the user asks about something you might have been told to remember, "
            "or when you need context about the user's preferences, projects, or workflow."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for in memory",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter",
                    "enum": ["preference", "person", "project", "location", "workflow", "fact"],
                },
            },
            "required": ["query"],
        },
    ),

    types.FunctionDeclaration(
        name="forget_memory",
        description=(
            "Delete a specific memory or all memories. "
            "Use when the user asks to forget something specific or clear all memories."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords matching the memory to forget, or 'everything' to clear all",
                },
            },
            "required": ["query"],
        },
    ),

    # --------------------------------------------------------
    # Editor / IDE
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="ide_context",
        description=(
            "Get what the user is currently looking at in their code editor: "
            "the project, the open file, the cursor position, any selected "
            "code, and the errors or warnings the editor is reporting. "
            "Use this when the user asks about 'this file', 'this code', "
            "'this error', or what they're working on."
        ),
    ),

    types.FunctionDeclaration(
        name="ide_open_file",
        description=(
            "Open a file in the user's editor, optionally jumping to a line. "
            "Use this to show the user something, not to read a file — "
            "use read_file when you need the contents yourself."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path of the file to open",
                },
                "line": {
                    "type": "integer",
                    "description": "Optional line number to jump to",
                },
            },
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="ide_apply_edit",
        description=(
            "Replace the user's current selection, or the whole open document, "
            "with new text in the editor. Use this for edits to a file the "
            "user has open so they see the change live."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path of the file to edit",
                },
                "text": {
                    "type": "string",
                    "description": "The new text to write in",
                },
                "replace_selection": {
                    "type": "boolean",
                    "description": (
                        "True to replace only the user's current selection, "
                        "false to replace the entire document"
                    ),
                },
            },
            "required": ["path", "text"],
        },
    ),

    # --------------------------------------------------------
    # Vision
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="see_screen",
        description=(
            "Capture and analyze the user's current screen. "
            "Use this when the user asks you to look at, see, inspect, or describe "
            "what is on their screen, or asks about errors, text, or apps visible on screen."
        ),
    ),

]


GEMINI_TOOLS = [types.Tool(function_declarations=TOOL_DECLARATIONS)]


# ============================================================
# Dispatch: function_name → (tool_name, action_name)
# ============================================================

DISPATCH = {
    "open_browser":   ("browser",    "open_browser"),
    "open_url":       ("browser",    "open_url"),
    "search_web":     ("browser",    "search"),
    "create_folder":  ("filesystem", "create_folder"),
    "create_file":    ("filesystem", "create_file"),
    "read_file":      ("filesystem", "read_file"),
    "write_file":     ("filesystem", "write_file"),
    "list_directory": ("filesystem", "list_directory"),
    "delete_path":    ("filesystem", "delete"),
    "run_command":    ("terminal",   "run"),
    "run_background": ("terminal",   "run_background"),
    "open_application": ("system",   "open_application"),
    "read_document":  ("document",   "read_document"),
    "search_files":   ("search",     "search_files"),
    "see_screen":     ("vision",     "see_screen"),
    "ide_context":    ("ide",        "get_context"),
    "ide_open_file":  ("ide",        "open_file"),
    "ide_apply_edit": ("ide",        "apply_edit"),
}

MEMORY_TOOLS = frozenset({"remember", "recall_memory", "forget_memory"})


# ============================================================
# Safety
# ============================================================

_CONFIRM_ACTIONS = frozenset({
    "write_file",
    "delete_path",
    "run_command",
    # Starting a detached process is still executing a command on the user's
    # machine — same gate as run_command, deliberately.
    "run_background",
    # Editing the user's open document changes their code — same gate as any
    # other write, deliberately not a separate confirmation path.
    "ide_apply_edit",
})


def needs_confirmation(function_name: str, args: dict) -> bool:
    return function_name in _CONFIRM_ACTIONS


def friendly_tool_name(function_name: str, args: dict) -> str:
    labels = {
        "open_browser": "Opening browser",
        "open_url": f"Opening {args.get('url', 'URL')}",
        "search_web": f"Searching the web for {args.get('query', '...')}",
        "create_folder": f"Creating folder {args.get('path', '')}",
        "create_file": f"Creating file {args.get('path', '')}",
        "read_file": f"Reading {args.get('path', '')}",
        "write_file": f"Writing to {args.get('path', '')}",
        "list_directory": f"Listing {args.get('path', '')}",
        "delete_path": f"Deleting {args.get('path', '')}",
        "run_command": f"Running: {args.get('command', '')}",
        "run_background": f"Starting: {args.get('command', '')}",
        "open_application": f"Opening {args.get('name', 'application')}",
        "read_document": f"Reading document {args.get('path', '')}",
        "search_files": f"Searching for {args.get('query', '...')}",
        "see_screen": "Looking at your screen",
        "ide_context": "Checking your editor",
        "ide_open_file": f"Opening {args.get('path', '')} in your editor",
        "ide_apply_edit": f"Editing {args.get('path', '')} in your editor",
        "remember": "Saving to memory",
        "recall_memory": "Searching memory",
        "forget_memory": "Forgetting memory",
    }
    return labels.get(function_name, f"Executing {function_name}")


def describe_action(function_name: str, args: dict) -> str:
    if function_name == "ide_apply_edit":
        scope = (
            "Replace the selected code in"
            if args.get("replace_selection")
            else "Replace the entire contents of"
        )
        preview = (args.get("text") or "").strip()
        if len(preview) > 400:
            preview = preview[:400] + "\n…"
        return f"{scope}: {args.get('path', '?')}\n\nNew content:\n{preview}"

    if function_name == "write_file":
        return f"Write to file: {args.get('path', '?')}"
    if function_name == "delete_path":
        return f"Delete: {args.get('path', '?')}"
    if function_name == "run_command":
        return f"Run terminal command:\n{args.get('command', '?')}"

    if function_name == "run_background":
        where = args.get("cwd")
        location = f"\nin {where}" if where else ""
        return f"Start this process and leave it running:\n{args.get('command', '?')}{location}"
    return f"Execute: {function_name}"


# ============================================================
# Ollama / OpenAI-format tool definitions
# ============================================================

def _to_ollama_tool(decl: types.FunctionDeclaration) -> dict:
    func = {"name": decl.name, "description": decl.description}
    if decl.parameters_json_schema:
        func["parameters"] = decl.parameters_json_schema
    else:
        func["parameters"] = {"type": "object", "properties": {}}
    return {"type": "function", "function": func}


OLLAMA_TOOLS = [_to_ollama_tool(d) for d in TOOL_DECLARATIONS]
