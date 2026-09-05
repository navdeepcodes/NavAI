from __future__ import annotations

from google.genai import types


# ============================================================
# Mike's canonical tool definitions. Provider-neutral: each brain's provider
# translates these into whatever protocol it speaks. Named after no vendor.
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
                    "description": (
                        "Directory to run the command in. Set this whenever the "
                        "work belongs to a particular folder — without it the "
                        "command runs wherever Mike was started, which is "
                        "almost never what you want."
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "Seconds to allow before the command is stopped. "
                        "Defaults to 60; raise it for a slow build or test run."
                    ),
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
        name="calculate",
        description=(
            "Work out an arithmetic expression exactly. Use this for any number "
            "that matters — a total, a difference, a percentage, a sum of a column "
            "you just read — rather than doing it in your head, where you will "
            "occasionally be wrong in a way that looks right. "
            "Give a plain expression, for example '2417 + 3168 + 912' or "
            "'round(4820 / 6, 2)'. Available functions: sum, min, max, abs, round, "
            "sqrt, floor, ceil."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The arithmetic to evaluate, e.g. '2417 + 3168 + 912'",
                },
            },
            "required": ["expression"],
        },
    ),

    types.FunctionDeclaration(
        name="read_spreadsheet",
        description=(
            "Read a spreadsheet as a grid of addressed cells (.xlsx, .xlsm, .csv). "
            "Use this instead of read_document whenever the work involves particular "
            "cells: reading a column of figures, checking a total, or before changing "
            "anything. It returns the grid, the formulas each cell contains, and says "
            "explicitly when a formula's calculated value is not stored in the file."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the spreadsheet"},
                "sheet": {
                    "type": "string",
                    "description": "Sheet name; omit for the first/active sheet",
                },
            },
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="edit_spreadsheet",
        description=(
            "Set the contents of specific cells in a spreadsheet and save it. "
            "Give cells as an object keyed by cell reference, for example "
            '{\"B6\": 4820, \"A6\": \"Total\", \"C6\": \"=SUM(C2:C5)\"}. '
            "A value starting with '=' is stored as a formula. Mike does not "
            "calculate formulas, so if the user needs the number itself, work it "
            "out and write it as a value. The file is reopened after saving and the "
            "cells are checked, so a failure to store is reported rather than assumed "
            "to have worked."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the spreadsheet"},
                "cells": {
                    "type": "object",
                    "description": "Cell reference to new value, e.g. {\"B6\": 4820}",
                },
                "sheet": {
                    "type": "string",
                    "description": "Sheet name; omit for the first/active sheet",
                },
            },
            "required": ["path", "cells"],
        },
    ),

    types.FunctionDeclaration(
        name="search_files",
        description=(
            "Find files by NAME. Use this when you know roughly what a file is "
            "called but not where it is: 'find the quarterly report', 'find a "
            "PDF called invoice'. "
            "To search for text INSIDE files, use search_code instead — it is "
            "much faster and returns the matching lines, not just filenames."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Filename, or part of one",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: your home folder)",
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
            "Look at the screen with vision. This is SLOW — several seconds — "
            "because it runs an image through a vision model, so it is the "
            "fallback, not the default way to inspect an application.\n"
            "Use see_ui instead whenever you are operating an application: it "
            "reads the same interface as text in a fraction of a second and "
            "gives you clickable references.\n"
            "Use see_screen when: the user asks what is on their screen; "
            "see_ui returned nothing useful for the app you need; the content "
            "is drawn rather than built from controls (canvas, charts, images, "
            "video, games); you need to judge how something actually looks; or "
            "you need spatial layout the control list cannot express."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "purpose": {
                    "type": "string",
                    "description": (
                        "'controls' to list what can be interacted with (fast, "
                        "for operating an interface), or 'describe' for a prose "
                        "description (slower, for answering the user). Defaults "
                        "to 'describe'."
                    ),
                },
            },
        },
    ),

    # --------------------------------------------------------
    # Reading and editing code
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="read_lines",
        description=(
            "Read a file with line numbers, or a slice of one. Prefer this over "
            "read_file when you intend to edit the file, when you need to refer "
            "to specific lines, or when the file is large. Line numbers here "
            "match the ones in stack traces and compiler errors."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "offset": {
                    "type": "integer",
                    "description": "First line to show, 1-based. Defaults to 1.",
                },
                "limit": {
                    "type": "integer",
                    "description": "How many lines to show. Defaults to 400.",
                },
            },
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="edit_file",
        description=(
            "Change part of an existing file by replacing an exact snippet of "
            "text. This is the right way to modify a file — use it instead of "
            "write_file, which replaces the entire file and loses anything you "
            "do not re-emit. old_text must match the file exactly, including "
            "indentation, and must be unique. Returns a diff of what changed."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "old_text": {
                    "type": "string",
                    "description": (
                        "The exact text to find, including indentation. Include "
                        "enough surrounding context to make it unique in the file."
                    ),
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace it with. Empty string deletes it.",
                },
                "expect_count": {
                    "type": "integer",
                    "description": (
                        "Only set this to deliberately replace every occurrence, "
                        "when you already know how many there are."
                    ),
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
    ),

    types.FunctionDeclaration(
        name="multi_edit",
        description=(
            "Apply several edits to one file at once, all or nothing. Use this "
            "for related changes that must land together. If any edit fails to "
            "match, none are applied and the file is left untouched."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "edits": {
                    "type": "array",
                    "description": "Edits applied in order; later edits see earlier ones.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_text": {"type": "string"},
                            "new_text": {"type": "string"},
                        },
                        "required": ["old_text", "new_text"],
                    },
                },
            },
            "required": ["path", "edits"],
        },
    ),

    # --------------------------------------------------------
    # Understanding a project
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="project_overview",
        description=(
            "Understand an unfamiliar project quickly: what kind of project it "
            "is, its dependencies and scripts, git branch and uncommitted "
            "changes, recent commits, and which files were modified most "
            "recently. Start here when asked about a codebase you have not "
            "looked at yet."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Project root. Defaults to the current directory.",
                },
            },
        },
    ),

    types.FunctionDeclaration(
        name="project_tree",
        description=(
            "Show a project's directory structure, depth-limited and with noise "
            "like node_modules and __pycache__ filtered out."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to show."},
                "max_depth": {
                    "type": "integer",
                    "description": "How deep to descend. Defaults to 3.",
                },
            },
        },
    ),

    types.FunctionDeclaration(
        name="search_code",
        description=(
            "Search inside files and get back file:line:text for each match. "
            "Use this to find where something is defined or used. Prefer it "
            "over search_files, which only returns filenames."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text to search for"},
                "path": {"type": "string", "description": "Where to search. Defaults to the current directory."},
                "file_glob": {
                    "type": "string",
                    "description": "Limit to matching files, e.g. '*.py'",
                },
                "regex": {
                    "type": "boolean",
                    "description": "Treat the query as a regular expression.",
                },
            },
            "required": ["query"],
        },
    ),

    # --------------------------------------------------------
    # Processes Mike started
    # --------------------------------------------------------

    # --------------------------------------------------------
    # Verifying that something actually worked
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="check_url",
        description=(
            "Fetch a URL and report the HTTP status and page content. Use this "
            "to confirm a server you started is actually serving, or that a page "
            "contains what you expect. A connection failure is a useful answer, "
            "not an error — it tells you the server isn't up yet."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch, e.g. http://localhost:8000"},
                "expect": {
                    "type": "string",
                    "description": "Optional text you expect to find in the response body.",
                },
            },
            "required": ["url"],
        },
    ),

    types.FunctionDeclaration(
        name="check_port",
        description=(
            "Check whether anything is listening on a port. The quickest way to "
            "tell whether a server you started came up."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "Port number"},
                "host": {"type": "string", "description": "Defaults to 127.0.0.1"},
            },
            "required": ["port"],
        },
    ),

    types.FunctionDeclaration(
        name="check_syntax",
        description=(
            "Check that a file still parses after you edited it. Editing a file "
            "successfully does not mean the result is still valid code. Supports "
            "Python, JSON and JavaScript."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File to check"}},
            "required": ["path"],
        },
    ),

    types.FunctionDeclaration(
        name="list_processes",
        description=(
            "List the background processes you started this session and whether "
            "each is still running. Use this to check whether a server you "
            "started is actually up."
        ),
    ),

    types.FunctionDeclaration(
        name="process_output",
        description=(
            "Read what a background process you started has printed. Use this to "
            "find out why a server failed to start, or to confirm it is ready."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "Process id from run_background"},
            },
            "required": ["pid"],
        },
    ),

    types.FunctionDeclaration(
        name="kill_process",
        description="Stop a background process you started.",
        parameters_json_schema={
            "type": "object",
            "properties": {
                "pid": {"type": "integer", "description": "Process id from run_background"},
            },
            "required": ["pid"],
        },
    ),

    # --------------------------------------------------------
    # Computer control
    #
    # Primitives for operating an interface that exposes no API. They are
    # deliberately small and composable: there is no "send_an_email" tool
    # here, because the moment one exists Mike stops being a general agent
    # and starts being a collection of application scripts.
    #
    # see_ui reads the accessibility tree, which is text rather than pixels.
    # It is roughly a thousand times cheaper than a screenshot through a
    # vision model and it names controls instead of guessing at them, so it
    # is the first thing to reach for. see_screen remains for interfaces the
    # accessibility tree cannot describe.
    # --------------------------------------------------------

    types.FunctionDeclaration(
        name="send_email",
        description=(
            "Send an email, optionally with file attachments. This goes out "
            "over the account's mail API, so it is reliable — prefer it over "
            "driving a webmail interface by hand.\n"
            "Sending is irreversible and leaves the machine, so the user is "
            "asked to confirm first and is shown the exact recipient, subject "
            "and attachments. Compose the whole message in one call; there is "
            "no separate draft step."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Subject line"},
                "body": {"type": "string", "description": "Plain-text body"},
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Absolute paths of files to attach",
                },
            },
            "required": ["to", "subject", "body"],
        },
    ),

    types.FunctionDeclaration(
        name="see_ui",
        description=(
            "Read the controls in an application's window: buttons, text fields, "
            "links, checkboxes, tabs, with their labels and current values. Each "
            "gets a reference like 'el7' that you pass to click_element or "
            "scroll_ui. ALWAYS prefer this over see_screen for operating an "
            "application: it is far faster, it names controls exactly, and it "
            "tells you whether they are enabled. Observe again after any action "
            "that changes the screen, because references go stale."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "app": {
                    "type": "string",
                    "description": (
                        "Application name, e.g. 'Safari'. Omit for whatever is "
                        "frontmost."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum controls to return (default 60).",
                },
            },
        },
    ),

    types.FunctionDeclaration(
        name="click_element",
        description=(
            "Click a control. Give the 'ref' from see_ui whenever you can — it is "
            "checked against a real element and fails clearly if the interface "
            "moved. Coordinates are a fallback for things the accessibility tree "
            "cannot see. Observe again afterwards to confirm what changed."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Element reference from see_ui, e.g. 'el7'"},
                "x": {"type": "integer", "description": "Screen x, only if no ref is available"},
                "y": {"type": "integer", "description": "Screen y, only if no ref is available"},
                "button": {"type": "string", "description": "'left' (default) or 'right'"},
                "count": {"type": "integer", "description": "1 for a click, 2 to double-click"},
            },
        },
    ),

    types.FunctionDeclaration(
        name="type_text",
        description=(
            "Type text into whatever currently has keyboard focus. Click the "
            "field first. This types characters exactly as given, including "
            "accents and other scripts; for keys with no character such as Enter "
            "or Tab use press_keys."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to type"},
            },
            "required": ["text"],
        },
    ),

    types.FunctionDeclaration(
        name="press_keys",
        description=(
            "Press a named key, optionally with modifiers — Enter, Tab, Escape, "
            "arrows, or a shortcut like cmd+s. Use type_text for ordinary "
            "characters."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key name: return, tab, escape, space, delete, up, down, left, right, a-z, 0-9, f1-f12",
                },
                "modifiers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Any of: cmd, shift, alt, ctrl, fn",
                },
            },
            "required": ["key"],
        },
    ),

    types.FunctionDeclaration(
        name="scroll_ui",
        description=(
            "Scroll the interface. Negative dy scrolls down, positive scrolls up. "
            "Use this to bring controls into view when what you need is not in "
            "the observation."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "dy": {"type": "integer", "description": "Vertical pixels; negative scrolls down"},
                "dx": {"type": "integer", "description": "Horizontal pixels"},
                "ref": {"type": "string", "description": "Scroll with the pointer over this element"},
            },
        },
    ),

    types.FunctionDeclaration(
        name="list_windows",
        description=(
            "List the open windows with their applications and titles. Use this "
            "to find out what is available before switching, or to confirm a "
            "window or dialog actually appeared."
        ),
    ),

    types.FunctionDeclaration(
        name="focus_app",
        description=(
            "Bring an already-running application to the front so it receives "
            "clicks and keystrokes. To start one that is not running, use "
            "open_application first."
        ),
        parameters_json_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Application name, e.g. 'Safari'"},
            },
            "required": ["name"],
        },
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
    # Targeted edits change the user's files just as much as a whole-file
    # write does. They go through the same single gate rather than earning an
    # exemption for being smaller.
    "edit_file",
    "multi_edit",
    # Stopping a process is disruptive and not always recoverable — whatever
    # it was doing is interrupted.
    "kill_process",
    # Starting a detached process is still executing a command on the user's
    # machine — same gate as run_command, deliberately.
    "run_background",
    # Editing the user's open document changes their code — same gate as any
    # other write, deliberately not a separate confirmation path.
    "ide_apply_edit",
    # Mail leaves the machine and cannot be recalled. Composing is free;
    # sending is the boundary.
    "send_email",
    # Changing cells overwrites a file the user already has, exactly like
    # write_file does, and a spreadsheet has no revision history to fall back
    # on. Reading one is free.
    "edit_spreadsheet",
    # Memory is user data with no undo and no copy on disk to restore from.
    # Saving and recalling stay free; erasing is the boundary, exactly as it
    # is for files. "forget everything" reaching the database unprompted was
    # the last ungated destructive tool.
    "forget_memory",
})


def needs_confirmation(function_name: str, args: dict) -> bool:
    if function_name in _CONFIRM_ACTIONS:
        return True

    # Clicking is how Mike operates any interface, so gating every click would
    # make ordinary work impossible -- and a confirmation prompt that fires
    # constantly is one the user stops reading, which is worse than none.
    #
    # Instead the gate follows the *target*. A control labelled Send, Delete,
    # Pay or Publish is a point of no return whatever application it lives in,
    # so the rule is a property of the interface rather than a list of apps.
    # Mike can navigate, fill fields and prepare an action freely; the step
    # that cannot be taken back still stops for the user.
    #
    # This narrows the blast radius, it does not eliminate it: an unlabelled
    # button cannot be judged this way. The limit is documented rather than
    # papered over.
    if function_name == "click_element" and args.get("ref"):
        try:
            from computer.session import SESSION

            return SESSION.irreversible_target(str(args["ref"])) is not None
        except Exception:
            # If the target cannot be identified, assume it matters.
            return True

    # A click by raw coordinates cannot be checked against anything at all.
    if function_name == "click_element" and (args.get("x") is not None or args.get("y") is not None):
        return True

    return False


def confirmation_detail(function_name: str, args: dict) -> str:
    """What the user is actually being asked to allow.

    "Allow click_element?" tells them nothing. "Click button 'Send'" tells
    them what will happen.
    """
    if function_name == "send_email":
        # The recipient and attachments are read back from the message that
        # would actually be sent, not from the model's description of it. A
        # confirmation that restates the model's intent verifies nothing.
        import os

        to = str(args.get("to") or "(no recipient)")
        subject = str(args.get("subject") or "(no subject)")
        files = []
        for path in (args.get("attachments") or []):
            resolved = os.path.abspath(os.path.expanduser(str(path)))
            if os.path.isfile(resolved):
                size = os.path.getsize(resolved)
                files.append(f"{os.path.basename(resolved)} ({size / 1024:.0f} KB)")
            else:
                files.append(f"{path} — MISSING")
        attached = ", ".join(files) if files else "no attachments"
        body = str(args.get("body") or "")
        return (
            f"Send an email to {to}\n"
            f"  subject: {subject}\n"
            f"  attachments: {attached}\n"
            f"  body starts: {body[:120]!r}\n"
            "This leaves the machine and cannot be recalled."
        )

    if function_name == "edit_spreadsheet":
        # Current values come from the file, so the user sees what is being
        # overwritten rather than only what it is being replaced with. A cell
        # holding an existing figure is the one worth stopping for.
        path = str(args.get("path") or "?")
        cells = args.get("cells") or {}
        current = {}
        try:
            from tools.filesystem import spreadsheet

            sheet = spreadsheet.read_sheet(path, args.get("sheet"))
            current = {
                f"{column}{row['row']}": value
                for row in sheet["rows"]
                for column, value in row["cells"].items()
            }
        except Exception:
            # An unreadable file is not a reason to skip the prompt; it is a
            # reason to say the before-values are unknown.
            current = {}

        lines = []
        for ref in sorted(cells):
            was = current.get(str(ref).upper())
            if was is None:
                lines.append(f"  • {ref}: (empty) → {cells[ref]!r}")
            else:
                lines.append(f"  • {ref}: {was!r} → {cells[ref]!r}")
        listed = "\n".join(lines[:15])
        if len(lines) > 15:
            listed += f"\n  … and {len(lines) - 15} more"
        return (
            f"Change {len(cells)} cell(s) in {path}"
            + (f" (sheet {args['sheet']})" if args.get("sheet") else "")
            + f":\n{listed}\nThe file is saved in place."
        )

    if function_name == "forget_memory":
        # Built from the database by the same selector that will do the
        # deleting, so the user is shown the actual rows at risk rather than
        # the model's account of them. A confirmation that restates the
        # request verifies nothing.
        try:
            from brain import memory_store

            preview = memory_store.preview_forget(query=str(args.get("query") or ""))
        except Exception as exc:
            return (
                f"Forget memories matching {args.get('query')!r}, but the "
                f"memories could not be read first to show you ({exc}). "
                "Allowing this deletes without a preview."
            )

        if preview.get("status") != "success":
            return f"Forget memories: {preview.get('error')}"

        rows = preview.get("memories") or []
        if not rows:
            return (
                f"Forget {preview.get('scope')} — nothing currently matches, "
                "so this would delete nothing."
            )

        listed = "\n".join(f"  • [{r['category']}] {r['content'][:100]}" for r in rows[:10])
        if len(rows) > 10:
            listed += f"\n  … and {len(rows) - 10} more"
        return (
            f"Permanently delete {len(rows)} memory(s) — {preview.get('scope')}:\n"
            f"{listed}\n"
            "This cannot be undone."
        )

    if function_name != "click_element":
        return ""
    try:
        from computer.session import SESSION

        ref = args.get("ref")
        if ref:
            phrase = SESSION.irreversible_target(str(ref))
            target = SESSION.describe_element(str(ref))
            if phrase:
                return f"This clicks {target} — a '{phrase}' action that cannot be undone."
            return f"This clicks {target}."
        return (
            f"This clicks screen position ({args.get('x')}, {args.get('y')}), which "
            "was not checked against a named control."
        )
    except Exception:
        return ""


# Built once from the declarations the model is actually given, so it can
# never drift from them.
_SCHEMAS: dict[str, dict] = {
    d.name: (d.parameters_json_schema or {}) for d in TOOL_DECLARATIONS
}


# What each JSON-schema type will accept from a model. Values that convert
# losslessly are fine -- "5" for an integer is unambiguous and models produce
# it constantly. Values that do not convert are refused rather than coerced
# into something arbitrary, because guessing what `pid="soon"` meant is how a
# tool ends up acting on the wrong thing.
def _coerces(value, want: str) -> bool:
    if want in ("integer", "number"):
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        try:
            float(str(value))
            return True
        except (TypeError, ValueError):
            return False
    if want == "array":
        return isinstance(value, (list, tuple))
    if want == "boolean":
        return isinstance(value, bool) or str(value).lower() in ("true", "false")
    if want == "object":
        return isinstance(value, dict)
    if want == "string":
        return not isinstance(value, (list, dict))
    return True


def _check_types(function_name: str, properties: dict, supplied: dict) -> str | None:
    """Refuse a value that cannot be what the parameter is declared to be."""
    for name, value in supplied.items():
        want = (properties.get(name) or {}).get("type")
        if not want or _coerces(value, want):
            continue
        return (
            f"{function_name} expects {name} to be {'an' if want[0] in 'aeiou' else 'a'} "
            f"{want}, but got {type(value).__name__} {value!r}. Nothing was "
            "executed and nothing changed. Call it again with the right type."
        )
    return None


def check_arguments(function_name: str, args: dict) -> str | None:
    """
    Returns an actionable message when a call can't succeed as written, or
    None when it looks fine.

    Exists because the previous failure mode was the single string
    "Validation failed." — which told the model nothing about what was wrong,
    so it had no way to correct itself and simply gave up. Naming the missing
    parameter and what was actually passed turns a dead end into something
    recoverable. This validates against the same schema the model was given,
    rather than second-guessing its intent.
    """
    if function_name not in _SCHEMAS:
        return None

    schema = _SCHEMAS.get(function_name) or {}
    # A tool that declares no parameters accepts none. Returning early on a
    # missing schema meant every argument-less tool -- open_browser,
    # list_windows, list_processes, ide_context -- silently swallowed whatever
    # it was sent, which is the same class of bug as run_command discarding
    # `path`: the call appears to work and does something other than asked.
    properties = schema.get("properties", {}) or {}
    required = schema.get("required", []) or []
    supplied = {k: v for k, v in (args or {}).items() if v is not None and v != ""}

    missing = [r for r in required if r not in supplied]
    known = ", ".join(sorted(properties)) or "(none)"
    given = ", ".join(sorted(supplied)) or "(none)"
    unexpected = [k for k in supplied if k not in properties]

    # An unrecognised parameter is refused rather than quietly dropped, even
    # when everything required is present. Observed for real: a model called
    # run_command with `path` (meaning the working directory) instead of
    # `cwd`. Required args were satisfied, so the call ran — with `path`
    # silently discarded and cwd defaulting to Mike's own source directory,
    # writing the user's files into the application's tree. Executing a
    # command somewhere other than where it was asked for is worse than not
    # executing it, so this refuses and says which name to use instead.
    if unexpected and not missing:
        return (
            f"{function_name} does not take {', '.join(sorted(unexpected))}. "
            f"Accepted parameters are: {known}. Nothing was executed and "
            "nothing changed. Call it again using only those parameters — if "
            "you meant to choose a working directory, that parameter is "
            f"{'cwd' if 'cwd' in properties else 'not available on this tool'}."
        )

    if not missing:
        return _check_types(function_name, properties, supplied)

    message = (
        f"{function_name} needs {', '.join(missing)}, which "
        f"{'was' if len(missing) == 1 else 'were'} not provided. "
        f"You passed: {given}. Accepted parameters are: {known}."
    )
    if unexpected:
        message += (
            f" These are not parameters of {function_name}: {', '.join(sorted(unexpected))}."
        )

    # Stating that nothing ran, and that a corrected retry is safe, is part of
    # a useful error — without it a recoverable mistake reads like a dead end
    # and the turn ends in a question to the user instead of a fix.
    message += (
        " Nothing was executed and nothing changed, so it is safe to call it "
        "again with the correct parameters."
    )
    return message


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
        "calculate": f"Working out {args.get('expression', '')}",
        "read_spreadsheet": f"Reading spreadsheet {args.get('path', '')}",
        "edit_spreadsheet": f"Updating spreadsheet {args.get('path', '')}",
        "search_files": f"Searching for {args.get('query', '...')}",
        "see_screen": "Looking at your screen",
        "ide_context": "Checking your editor",
        "ide_open_file": f"Opening {args.get('path', '')} in your editor",
        "ide_apply_edit": f"Editing {args.get('path', '')} in your editor",
        "remember": "Saving to memory",
        "recall_memory": "Searching memory",
        "forget_memory": "Forgetting memory",
        "read_lines": f"Reading {args.get('path', '')}",
        "edit_file": f"Editing {args.get('path', '')}",
        "multi_edit": f"Editing {args.get('path', '')}",
        "project_overview": "Looking over the project",
        "project_tree": "Mapping the project structure",
        "search_code": f"Searching the code for {args.get('query', '...')}",
        "list_processes": "Checking what's running",
        "check_url": f"Checking {args.get('url', 'a URL')}",
        "check_port": f"Checking port {args.get('port', '')}",
        "check_syntax": f"Checking {args.get('path', '')} parses",
        "process_output": f"Reading output from process {args.get('pid', '')}",
        "kill_process": f"Stopping process {args.get('pid', '')}",
    }
    return labels.get(function_name, f"Executing {function_name}")


def describe_action(function_name: str, args: dict) -> str:
    # The richer descriptions live in confirmation_detail because they need to
    # inspect real state -- files on disk, the observed element -- rather than
    # restate the arguments. Route to it first, so what the user is shown is
    # what will actually happen.
    detailed = confirmation_detail(function_name, args)
    if detailed:
        return detailed

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

    if function_name == "edit_file":
        old = (args.get("old_text") or "").strip()
        new = (args.get("new_text") or "").strip()
        if len(old) > 300:
            old = old[:300] + "\n…"
        if len(new) > 300:
            new = new[:300] + "\n…"
        return (
            f"Edit {args.get('path', '?')}\n\nReplace:\n{old}\n\nWith:\n{new}"
        )

    if function_name == "multi_edit":
        edits = args.get("edits") or []
        return f"Apply {len(edits)} edit(s) to: {args.get('path', '?')}"

    if function_name == "kill_process":
        return f"Stop the process with pid {args.get('pid', '?')}"

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
