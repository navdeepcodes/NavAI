from __future__ import annotations

import json
import pathlib
import platform
import threading
from datetime import datetime
from typing import Callable

import ollama

from brain.core_tools import (
    DISPATCH,
    MEMORY_TOOLS,
    OLLAMA_TOOLS,
    describe_action,
    friendly_tool_name,
    needs_confirmation,
)
from brain import environment, memory_store
from brain.mike_core import MikeCore
from config.ollama import OLLAMA_HOST, OLLAMA_SUMMARY_MODEL
from core.tool_executor import ToolExecutor
from logs.logger import logger
from vision.vision import Vision

MAX_AGENT_STEPS = 12

OLLAMA_MODEL = "qwen3:8b"

SYSTEM_PROMPT = f"""\
You are Mike, a helpful AI assistant that lives on the user's Mac desktop.

You can have normal conversations AND control the computer using tools \
(opening websites, managing files, running terminal commands, reading documents, \
searching through files, and working with code).

How to behave:
- Talk like a friendly, smart person. Be warm, concise, and natural.
- For casual messages ("hey", "how are you", "what's up"), just chat naturally. \
You're not a command processor — you're a person to talk to.
- When the user wants something done on their computer, use the right tool. \
After it works, confirm briefly ("Done — opened YouTube" or "Created the folder").
- If something fails, say what happened plainly.
- Never make up that you did something you didn't. This applies especially to memory: \
only say something is remembered, saved, or noted for later if the remember tool actually \
ran and succeeded. A casual acknowledgment of something the user said is not the same as \
saving it — don't phrase the two the same way.
- Never expose internal tool names, function names, or system details.
- If you're not confident what the user means, say so and ask a short clarifying question, \
or explain what's missing. Never send back an empty or blank reply — always say something, \
even if it's just admitting you're unsure.
- Keep responses short. Don't over-explain. One or two sentences is usually enough \
for conversation. A bit more is fine when the user asks a real question.
- Your responses are spoken aloud, so write naturally. \
Avoid emojis, bullet lists, Markdown formatting, and giant code blocks in conversational replies. \
Use plain sentences. For code, put it in a code block but keep your explanation conversational.

Documents & Code:
- You can read PDF, DOCX, PPTX, CSV, JSON, and all text files. \
Use read_document for document files. Use read_file for quick text file reads.
- You can search inside files using search_files. Use it to find code, text, or files by name.
- For code tasks: read the file first, understand it, then make changes with write_file. \
You can run tests or scripts with run_command. Chain multiple tools to debug, modify, and verify.
- When explaining code, focus on what matters: purpose, key logic, potential issues. \
Don't just repeat the code back.

Memory:
- You have persistent memory across restarts. You can remember facts the user tells you.
- When the user says "remember that...", "don't forget...", "save this...", or "keep in mind...", \
use the remember tool to save it. Only after that tool call actually succeeds, confirm with \
something like "Got it, I'll remember that." If you didn't call the tool, don't say that phrase — \
just acknowledge normally ("Got it.") without implying it was saved anywhere permanent.
- When the user asks about something you might know from memory (preferences, projects, locations), \
use recall_memory to check. Answer naturally using what you find.
- When the user says "forget...", "delete...", or "clear my memories", use forget_memory.
- For "what do you remember?" or "what do you know about me?", use recall_memory with no query \
to list everything, then summarize naturally.
- NEVER use remember for normal conversation or tool requests. Only for explicit "remember" requests. \
This also means: don't casually say "I'll remember that" while chatting about something the user \
mentioned in passing — that phrase is reserved for when you actually called the remember tool.

Working toward a goal:
- When the user gives you something to accomplish rather than a single command, work through it: \
take an action, look at what happened, and decide the next step yourself. Don't stop after one \
step if the goal clearly needs more.
- Before treating something as done, check that it actually happened — especially for anything \
that changes files or runs code. Executing an action and confirming its outcome are different things.
- If a step fails, look at why and try a reasonable fix before giving up. Say plainly if you get \
stuck or run out of good options.
- Deleting, overwriting, or running system commands still needs confirmation first, even in the \
middle of a larger task — working toward a goal never skips that.
- If you're missing something you need to continue, ask instead of guessing.
- Stop and report clearly once the goal is met, once you're stuck, or once you run out of steps — \
never say something is finished when it isn't.

The user's home directory is {pathlib.Path.home()}.
Paths like "Desktop/folder" or "Documents/file.txt" are relative to home.

Today's date is {{date}}. Use this for any time-sensitive answers.\
"""


class CoreRuntime:
    """
    Mike's simplified runtime using Ollama with native tool calling.

    User → LLM (with tools) → Tool execution → LLM → User

    One LLM call for conversation.
    Two LLM calls for tool use (call + summary).
    """

    def __init__(self) -> None:

        logger.info("Initializing CoreRuntime...")

        self._client = ollama.Client(host=OLLAMA_HOST)

        self._tool_executor = ToolExecutor()

        self._core = MikeCore(host=OLLAMA_HOST, summary_model=OLLAMA_SUMMARY_MODEL)

        logger.info("CoreRuntime ready (model=%s).", OLLAMA_MODEL)

    # =====================================================
    # Startup
    # =====================================================

    def startup(self) -> str:

        hour = datetime.now().hour

        if hour < 12:
            greeting = "Good morning. Ready when you are."
        elif hour < 17:
            greeting = "Good afternoon. What are we working on?"
        elif hour < 21:
            greeting = "Good evening. Ready to continue?"
        else:
            greeting = "You're back. Ready when you are."

        self._core.history.append({"role": "assistant", "content": greeting})

        return greeting

    # =====================================================
    # Process
    # =====================================================

    def process(
        self,
        message: str,
        confirm_callback: Callable[[str], bool] | None = None,
    ) -> str:

        logger.info("Processing: %s", message)

        self._core.history.append({"role": "user", "content": message})

        self._core.trim_history()

        try:

            response = self._call_llm()

            reply = self._handle_response(
                response,
                confirm_callback,
            )

        except Exception:

            logger.exception("LLM call failed.")
            reply = "I'm sorry, I'm having trouble responding right now."

        self._core.note_turn_complete()

        logger.info("Response: %s", reply[:120])

        return reply

    # =====================================================
    # Streaming Process
    # =====================================================

    def process_streaming(
        self,
        message: str,
        confirm_callback: Callable[[str], bool] | None = None,
        cancel_event: threading.Event | None = None,
    ):
        logger.info("Processing (streaming): %s", message)

        self._core.history.append({"role": "user", "content": message})
        self._core.trim_history()

        try:
            yield from self._streaming_loop(confirm_callback, cancel_event)
        except Exception:
            logger.exception("LLM call failed.")
            yield ("text", "I'm sorry, I'm having trouble responding right now.")
        finally:
            self._core.note_turn_complete()

    def _streaming_loop(
        self,
        confirm_callback: Callable[[str], bool] | None,
        cancel_event: threading.Event | None = None,
        depth: int = 0,
    ):
        if cancel_event is not None and cancel_event.is_set():
            note = "Cancelled — stopped before starting the next step."
            self._core.history.append({"role": "assistant", "content": note})
            yield ("token", note)
            return

        messages = self._build_messages()

        collected_text = ""
        tool_calls_raw = []

        for chunk in self._client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=OLLAMA_TOOLS,
            think=False,
            stream=True,
            options={"temperature": 0.4, "num_ctx": 4096, "num_predict": 300},
        ):
            msg = chunk.message

            if msg.content:
                collected_text += msg.content
                yield ("token", msg.content)

            if msg.tool_calls:
                tool_calls_raw.extend(msg.tool_calls)

        if not tool_calls_raw:
            self._core.history.append({"role": "assistant", "content": collected_text})
            return

        self._core.history.append({
            "role": "assistant",
            "content": collected_text,
            "tool_calls": [
                {
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in tool_calls_raw
            ],
        })

        for tc in tool_calls_raw:
            name = tc.function.name
            args = tc.function.arguments or {}
            if isinstance(args, str):
                args = json.loads(args)

            logger.info("Tool call: %s(%s)", name, args)

            yield ("tool_start", friendly_tool_name(name, args))

            if needs_confirmation(name, args):
                if confirm_callback:
                    desc = describe_action(name, args)
                    if not confirm_callback(desc):
                        self._core.history.append({
                            "role": "tool",
                            "content": json.dumps({
                                "status": "cancelled",
                                "message": "User denied this action.",
                            }),
                        })
                        self._core.add_tool_result("Cancelled by user.")
                        yield ("tool_end", "Cancelled by user.")
                        continue

            result = self._execute_tool(name, args)

            self._core.history.append({
                "role": "tool",
                "content": json.dumps(result),
            })

            status = result.get("result", result.get("error", "Done"))
            self._core.add_tool_result(status)
            yield ("tool_end", status)

        if depth >= MAX_AGENT_STEPS:
            yield from self._wrap_up(
                "You've reached the step limit for this task. Stop taking "
                "further actions. Tell the user plainly, in one or two "
                "sentences, what you actually accomplished and what's still "
                "left, based on the steps above. Don't claim it's finished "
                "if it isn't."
            )
            return

        if len(tool_calls_raw) == 1 and depth == 0:
            last_tool = self._core.history[-1]
            if last_tool.get("role") == "tool":
                result = json.loads(last_tool["content"])
                if result.get("status") == "success":
                    tc = tool_calls_raw[0]
                    name = tc.function.name
                    args = tc.function.arguments or {}
                    if isinstance(args, str):
                        args = json.loads(args)
                    summary = _quick_summary(name, args)
                    if summary:
                        self._core.history.append({"role": "assistant", "content": summary})
                        yield ("token", summary)
                        return

        try:
            yield from self._streaming_loop(confirm_callback, cancel_event, depth + 1)
        except Exception:
            logger.exception("Follow-up LLM call failed.")
            note = "I ran into a problem partway through and had to stop there."
            self._core.history.append({"role": "assistant", "content": note})
            yield ("token", note)

    # =====================================================
    # Honest wrap-up (used when the step limit is reached)
    # =====================================================

    def _wrap_up(self, instruction: str):

        messages = self._build_messages()
        messages.append({"role": "user", "content": instruction})

        try:

            response = self._client.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                think=False,
                options={"temperature": 0.4, "num_ctx": 4096, "num_predict": 300},
            )

            text = response.message.content or "I wasn't able to finish this."

        except Exception:

            logger.exception("Wrap-up LLM call failed.")
            text = "I ran into trouble partway through and had to stop."

        self._core.history.append({"role": "assistant", "content": text})
        yield ("token", text)

    # =====================================================
    # LLM Call (non-streaming)
    # =====================================================

    def _call_llm(self) -> ollama.ChatResponse:

        messages = self._build_messages()

        return self._client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=OLLAMA_TOOLS,
            think=False,
            options={"temperature": 0.4, "num_ctx": 4096, "num_predict": 300},
        )

    # =====================================================
    # Response Handling
    # =====================================================

    def _handle_response(
        self,
        response: ollama.ChatResponse,
        confirm_callback: Callable[[str], bool] | None,
        depth: int = 0,
    ) -> str:

        message = response.message

        tool_calls = message.tool_calls or []

        if not tool_calls:
            text = message.content or ""
            self._core.history.append({"role": "assistant", "content": text})
            return text

        self._core.history.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:

            name = tc.function.name
            args = tc.function.arguments or {}
            if isinstance(args, str):
                args = json.loads(args)

            logger.info("Tool call: %s(%s)", name, args)

            if needs_confirmation(name, args):
                if confirm_callback:
                    desc = describe_action(name, args)
                    if not confirm_callback(desc):
                        self._core.history.append({
                            "role": "tool",
                            "content": json.dumps({
                                "status": "cancelled",
                                "message": "User denied this action.",
                            }),
                        })
                        continue

            result = self._execute_tool(name, args)

            self._core.history.append({
                "role": "tool",
                "content": json.dumps(result),
            })

        if depth >= MAX_AGENT_STEPS:
            return "I hit my step limit before finishing this."

        try:
            follow_up = self._call_llm()
            return self._handle_response(
                follow_up,
                confirm_callback,
                depth + 1,
            )
        except Exception:
            logger.exception("Follow-up LLM call failed.")
            return "I ran into a problem partway through and had to stop there."

    # =====================================================
    # Tool Execution
    # =====================================================

    def _execute_tool(
        self,
        function_name: str,
        args: dict,
    ) -> dict:

        if function_name in MEMORY_TOOLS:
            return self._execute_memory_tool(function_name, args)

        if function_name == "see_screen":
            return self._execute_vision(args)

        if function_name == "read_document":
            return self._execute_read_document(args)

        if function_name == "search_files":
            return self._execute_search_files(args)

        dispatch = DISPATCH.get(function_name)

        if not dispatch:
            logger.error("Unknown function: %s", function_name)
            return {"error": f"Unknown function: {function_name}"}

        tool_name, action = dispatch

        try:

            result = self._tool_executor.execute(
                tool_name=tool_name,
                action=action,
                **args,
            )

            if result.success:

                logger.info(
                    "Tool success: %s.%s → %s",
                    tool_name,
                    action,
                    result.message[:80] if result.message else "OK",
                )

                return {
                    "status": "success",
                    "result": result.message or "Done",
                    "data": result.data if result.data else None,
                }

            else:

                logger.warning(
                    "Tool failed: %s.%s → %s",
                    tool_name,
                    action,
                    result.error,
                )

                return {
                    "status": "error",
                    "error": result.error or "Tool execution failed",
                }

        except Exception as exc:

            logger.exception("Tool execution error: %s", exc)

            return {"status": "error", "error": str(exc)}

    # =====================================================
    # Documents
    # =====================================================

    def _execute_read_document(self, args: dict) -> dict:
        try:
            from tools.filesystem.document_reader import read_document
            path = args.get("path", "")
            if not path:
                return {"status": "error", "error": "No file path provided."}
            text = read_document(path)
            logger.info("Document read: %s (%d chars)", path, len(text))
            return {"status": "success", "result": text}
        except FileNotFoundError as exc:
            return {"status": "error", "error": str(exc)}
        except Exception as exc:
            logger.exception("Document read failed: %s", exc)
            return {"status": "error", "error": f"Could not read document: {exc}"}

    def _execute_search_files(self, args: dict) -> dict:
        import subprocess
        from tools.filesystem.path_utils import resolve_path

        query = args.get("query", "")
        if not query:
            return {"status": "error", "error": "No search query provided."}

        search_path = str(resolve_path(args.get("path", "Desktop")))
        file_type = args.get("file_type", "")

        try:
            if any(c in query for c in "*?["):
                cmd = ["find", search_path, "-name", query, "-type", "f"]
                if file_type:
                    cmd = ["find", search_path, "-name", f"*.{file_type}", "-type", "f"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                output = result.stdout.strip()
            else:
                cmd = ["grep", "-r", "-l", "-i", "--include", f"*.{file_type}" if file_type else "*", query, search_path]
                if not file_type:
                    cmd = ["grep", "-r", "-l", "-i", query, search_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                output = result.stdout.strip()

            if not output:
                return {"status": "success", "result": f"No matches found for '{query}' in {search_path}."}

            lines = output.split("\n")
            if len(lines) > 50:
                output = "\n".join(lines[:50]) + f"\n... and {len(lines) - 50} more files"

            logger.info("Search found %d results for '%s'", len(lines), query)
            return {"status": "success", "result": output}

        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Search took too long. Try a more specific path."}
        except Exception as exc:
            logger.exception("Search failed: %s", exc)
            return {"status": "error", "error": f"Search failed: {exc}"}

    # =====================================================
    # Vision
    # =====================================================

    def _execute_vision(self, args: dict) -> dict:

        try:
            vision = Vision()
            description = vision.describe_screen()

            logger.info("Vision result: %s", description[:120])

            if description:
                self._core.set_vision(description)

            return {
                "status": "success",
                "result": description or "I could see your screen but couldn't describe it.",
            }

        except Exception as exc:
            logger.exception("Vision failed: %s", exc)

            msg = str(exc)
            if "not found" in msg.lower():
                return {
                    "status": "error",
                    "error": "The vision model isn't installed. Please run: ollama pull qwen3.5:2b",
                }
            if "connection" in msg.lower() or "refused" in msg.lower():
                return {
                    "status": "error",
                    "error": "Can't reach Ollama. Make sure it's running.",
                }
            if "screen capture" in msg.lower() or "permission" in msg.lower():
                return {
                    "status": "error",
                    "error": "Screen capture failed. Check that screen recording permission is granted in System Settings → Privacy & Security.",
                }

            return {"status": "error", "error": f"Vision failed: {msg}"}

    # =====================================================
    # Helpers
    # =====================================================

    def _build_messages(self) -> list[dict]:
        last_user = ""
        for msg in reversed(self._core.history):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break

        memories = memory_store.auto_recall(last_user) if last_user else []

        prompt = SYSTEM_PROMPT.replace(
            "{date}", datetime.now().strftime("%A, %B %-d, %Y")
        )

        env_line = environment.describe_environment()

        if env_line:
            prompt += f"\n\n{env_line}"

        context_block = self._core.to_prompt_context()

        if context_block:
            prompt += f"\n\n{context_block}"

        if memories:
            mem_lines = [f"- [{m['category']}] {m['content']}" for m in memories]
            prompt += (
                "\n\nRelevant memories about this user:\n"
                + "\n".join(mem_lines)
                + "\nUse these naturally if relevant to the conversation."
            )

        return [{"role": "system", "content": prompt}, *self._core.history]

    def _execute_memory_tool(self, name: str, args: dict) -> dict:
        if name == "remember":
            return memory_store.remember(
                content=args.get("content", ""),
                category=args.get("category", "fact"),
            )
        if name == "recall_memory":
            return memory_store.recall(
                query=args.get("query", ""),
                category=args.get("category", ""),
            )
        if name == "forget_memory":
            return memory_store.forget(
                query=args.get("query", ""),
            )
        return {"status": "error", "error": f"Unknown memory tool: {name}"}


def _quick_summary(function_name: str, args: dict) -> str | None:
    """
    Short spoken summary for simple, self-contained tool calls, skipping the
    second LLM round. Returning None here forces a real follow-up turn instead —
    required for create_folder/create_file/delete_path, since those are often
    one step in a larger goal (create folder, write a file into it, verify) and
    the model needs to see the result to decide whether to continue.
    """
    if function_name == "open_browser":
        return "Done, opened the browser."
    if function_name == "open_url":
        url = args.get("url", "")
        if "youtube" in url.lower():
            return "Done, opened YouTube."
        if "google" in url.lower():
            return "Done, opened Google."
        if "github" in url.lower():
            return "Done, opened GitHub."
        if "reddit" in url.lower():
            return "Done, opened Reddit."
        if "twitter" in url.lower() or "x.com" in url.lower():
            return "Done, opened X."
        if "wikipedia" in url.lower():
            return "Done, opened Wikipedia."
        return "Done, opened the link."
    if function_name == "search_web":
        return None
    if function_name == "create_folder":
        return None
    if function_name == "create_file":
        return None
    if function_name == "delete_path":
        return None
    if function_name == "remember":
        return "Got it, I'll remember that."
    if function_name == "forget_memory":
        return None
    if function_name == "recall_memory":
        return None
    if function_name == "list_directory":
        return None
    if function_name == "run_command":
        return None
    return None
