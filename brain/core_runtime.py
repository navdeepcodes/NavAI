from __future__ import annotations

import json
from pathlib import Path
import pathlib
import threading
from datetime import datetime
from typing import Callable

from brain.context_budget import plan_request
from brain.providers import BrainError, ChatResult, get_provider
from brain.core_tools import (
    DISPATCH,
    MEMORY_TOOLS,
    OLLAMA_TOOLS,
    check_arguments,
    describe_action,
    friendly_tool_name,
    needs_confirmation,
)
from brain import environment, memory_store
from brain.mike_core import MikeCore
from config.ollama import (
    OLLAMA_CHAT_MODEL,
    OLLAMA_HOST,
    OLLAMA_SUMMARY_MODEL,
    OLLAMA_VISION_MODEL,
)
from core.tool_executor import ToolExecutor
from logs.logger import logger
from vision.vision import Vision

# Tools whose result is structured evidence the model needs intact — exit
# codes, diffs, numbered lines, live process state. Everything else still
# goes through the ToolResult path, which flattens a result to a string.
_COMPUTER_TOOLS = frozenset({
    "see_ui", "click_element", "type_text", "press_keys",
    "scroll_ui", "list_windows", "focus_app",
})

_DIRECT_TOOLS = frozenset({
    "run_command",
    "run_background",
    "list_processes",
    "process_output",
    "kill_process",
    "read_lines",
    "edit_file",
    "multi_edit",
    "project_overview",
    "project_tree",
    "search_code",
    "check_url",
    "check_port",
    "check_syntax",
    # Computer control returns structured evidence — which element was hit,
    # what the window now contains — and the model needs that intact to
    # verify its own actions rather than assume they landed.
    "see_ui",
    "click_element",
    "type_text",
    "press_keys",
    "scroll_ui",
    "list_windows",
    "focus_app",
    # Sending returns structured evidence read back from the mailbox, which
    # the model needs intact to know the attachment actually went.
    "send_email",
})

# Tools that _execute_tool routes itself rather than through DISPATCH,
# _DIRECT_TOOLS or the memory store. Named here rather than left implicit in
# the if-chain so that "is every declared tool actually reachable?" is a
# question the test suite can answer without a hand-maintained list that
# drifts the moment a tool is added.
_SPECIAL_TOOLS = frozenset({
    "calculate",
    "see_screen",
    "read_document",
    "read_spreadsheet",
    "edit_spreadsheet",
    "search_files",
})

# Context size and generation limits are provider concerns and live at the
# provider boundary: config.ollama.NUM_CTX is what reaches Ollama, and
# ollama_provider.DEFAULT_NUM_PREDICT is the generation cap. This module used
# to declare a second NUM_CTX = 8192 and GEN_OPTIONS with num_predict = 900.
# Nothing read them once the providers landed, but two tests still asserted
# against them, so the suite was guarding numbers no request ever used -- the
# same second-hardcoded-copy shape as the OLLAMA_MODEL bug this file already
# carried. Removed rather than updated: one owner per setting.

# Turns a single task may take before Mike stops and reports honestly.
#
# 12 was cutting real work short. Measured on the endurance task (understand a
# project, find a cross-file bug, fix it, add a function, prove both with the
# project's own tests): the local brain made its edit on step 12 and was
# stopped immediately afterwards, and DeepSeek needed 13 tool calls to finish
# the same task. A limit that ends a task at the moment it starts acting is
# too low.
#
# Still bounded — this is the backstop against a model looping forever, not a
# budget to be spent. Mike reports what it actually accomplished when it is
# reached rather than claiming success.
MAX_AGENT_STEPS = 20

# How many times a recoverable model/protocol failure is retried before the
# turn gives up. Small on purpose: this recovers a stochastic stumble, it does
# not paper over a backend that is actually down.
MAX_STREAM_RETRIES = 2

# The brain model comes from config, it is not restated here. This used to be
# a second hardcoded copy of the model name, which meant brain/diagnostics.py
# could check OLLAMA_CHAT_MODEL and report "the model is available" about a
# model the runtime never actually ran.
OLLAMA_MODEL = OLLAMA_CHAT_MODEL

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
- For spreadsheets (.xlsx, .csv), use read_spreadsheet rather than read_document when \
the work is about particular cells, and edit_spreadsheet to change them. \
You cannot calculate formulas. If you write =SUM(...), the file holds the formula but \
no number, and read_spreadsheet will tell you the value is not calculated — never state \
a total you have not worked out yourself. When the user needs the number, do the \
arithmetic and write the value, and add the formula as well if they asked for one.
- To change an existing file, use edit_file (or multi_edit for several related changes \
at once). Read the file first with read_lines so you can match the text exactly. \
Reserve write_file for creating a new file or deliberately replacing an entire one — \
it overwrites everything, so anything you don't re-emit is lost.
- If an edit reports that the text wasn't found or matched several places, nothing was \
changed. Read that part of the file again and retry with more surrounding context.
- To understand a project you haven't seen, start with project_overview, then \
project_tree or search_code. Don't read the whole repository.
- search_code searches inside files and gives you file:line:text. search_files only \
finds filenames.
- A tool call succeeding is not the same as the task succeeding. After editing \
code, check_syntax tells you whether the file still parses. After starting a \
server, check_port and check_url tell you whether it is actually serving. \
Verify before you say something is done.
- You are not reliable at arithmetic done in your head, and a total that is \
wrong by three looks exactly like a total that is right. Use calculate for any \
number that matters — summing a column, a difference, a percentage — and use \
the number it gives you.
- run_command gives you the exit code, stdout, and stderr. A non-zero exit code is \
information, not a dead end — read the output and decide what to do. Use run_background \
for anything that stays running, like a dev server, then list_processes or \
process_output to check on it.
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

        # The brain is obtained through the provider boundary. Nothing below
        # this line knows which backend or model is actually answering.
        self._brain = get_provider()
        self._capabilities = self._brain.capabilities()
        # Resolved lazily: only built if the brain itself can't see.
        self._vision_provider = None
        logger.info("Brain: %s", self._capabilities.explain())

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

        # Once per message: pick up whatever project is attached right now
        # and swap in that project's own situation summary if it's changed.
        self._core.sync_project()

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

        # Fit the request to this brain before sending it. Tool schemas are
        # never truncated — a model holding half a definition calls it wrongly.
        plan = plan_request(messages, OLLAMA_TOOLS, self._capabilities)
        if not plan.fits:
            note = plan.error.human()
            self._core.history.append({"role": "assistant", "content": note})
            yield ("token", note)
            return
        if plan.notes:
            logger.info("Context plan: %s", "; ".join(plan.notes))

        stream_failed: BrainError | None = None

        # A model that garbles its own tool-call syntax is producing noise,
        # not a decision — measured at roughly a third of calls for the
        # current local brain even with ample context. The provider already
        # marks such failures retry_safe; nothing was acting on it, so a
        # recoverable stumble ended the turn. Retried a bounded number of
        # times, and only when the attempt produced nothing at all, so no
        # partial output is ever duplicated and a genuinely broken backend
        # still surfaces quickly. Provider-neutral: any brain with stochastic
        # output benefits, none is special-cased.
        for attempt in range(MAX_STREAM_RETRIES + 1):
            collected_text = ""
            tool_calls_raw = []
            stream_failed = None
            truncated = False

            for event in self._brain.stream(plan.messages, plan.tools, cancel=cancel_event):
                if event.kind == "text":
                    collected_text += event.text
                    yield ("token", event.text)
                elif event.kind == "tool_call":
                    tool_calls_raw.append(event.tool_call)
                elif event.kind == "error":
                    stream_failed = event.error
                    break
                elif event.kind == "done":
                    truncated = event.truncated

            # A turn stopped by the token limit is not a finished answer. If it
            # produced nothing usable it is worth one more attempt, on exactly
            # the same terms as any other recoverable failure; if it did produce
            # output, that output is severed and the fact is recorded rather
            # than passed off as a clean completion.
            if truncated:
                logger.warning(
                    "The model's turn was cut off at the generation limit "
                    "(text=%d chars, tool calls=%d).",
                    len(collected_text), len(tool_calls_raw),
                )

            produced_nothing = not collected_text and not tool_calls_raw

            # The "produced nothing" rule exists so partial output is never
            # duplicated by a retry. It is the right rule for a truncated
            # turn, where the text so far may be a real partial answer.
            #
            # It was the wrong rule for a parse failure, and it made this
            # whole retry path dead in practice. Models write a sentence
            # before they call a tool -- "I'll open the spreadsheet and work
            # through this step by step" -- and that sentence counts as
            # output, so a recoverable protocol error ended the turn on the
            # first attempt with nothing done. Measured on a real run: one
            # turn, zero tool calls, eleven seconds, task abandoned.
            #
            # A protocol failure means the tool call never parsed, so nothing
            # was executed and nothing can happen twice. The preamble is not
            # an answer. The cost of retrying is that the reader may see that
            # sentence twice; the cost of not retrying is the task.
            protocol_stumble = (
                stream_failed is not None
                and stream_failed.kind == "protocol"
                and not tool_calls_raw
            )
            recoverable = (
                (stream_failed is not None and stream_failed.retry_safe or truncated)
                and (produced_nothing or protocol_stumble)
                and attempt < MAX_STREAM_RETRIES
                and not (cancel_event is not None and cancel_event.is_set())
            )
            if not recoverable:
                break

            logger.info(
                "Retrying after a recoverable model error (attempt %d/%d): %s",
                attempt + 1, MAX_STREAM_RETRIES,
                stream_failed.detail[:120] if stream_failed
                else "the turn was cut off at the generation limit",
            )

        if stream_failed is not None:
            # Model misbehaviour is reported, never executed and never raised.
            logger.warning("Brain error (%s): %s", stream_failed.kind, stream_failed.detail)
            note = stream_failed.human()
            self._core.history.append({"role": "assistant", "content": note})
            yield ("token", note)
            return

        if not tool_calls_raw:
            self._core.history.append({"role": "assistant", "content": collected_text})
            return

        self._core.history.append({
            "role": "assistant",
            "content": collected_text,
            # call_id is part of the canonical ToolCall and is preserved so
            # providers can correlate a tool result with the call that caused
            # it. Some backends require that correlation; Mike itself does not
            # care, and does not need to know which ones.
            "tool_calls": [
                {"id": tc.call_id, "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in tool_calls_raw
            ],
        })

        for tc in tool_calls_raw:
            # Already normalised at the provider boundary: name is a string,
            # arguments are a dict, whatever protocol the model spoke.
            name = tc.name
            args = tc.arguments or {}

            logger.info("Tool call: %s(%s)", name, args)

            yield ("tool_start", friendly_tool_name(name, args))

            if needs_confirmation(name, args):
                if confirm_callback:
                    desc = describe_action(name, args)
                    if not confirm_callback(desc):
                        self._core.history.append({
                            "role": "tool",
                            "tool_call_id": tc.call_id,
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
                "tool_call_id": tc.call_id,
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
                    summary = _quick_summary(tc.name, tc.arguments or {})
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

            plan = plan_request(messages, None, self._capabilities)
            result = self._brain.complete(plan.messages, None)
            if result.error is not None:
                logger.warning("Wrap-up failed: %s", result.error.detail)
                text = "I ran into trouble partway through and had to stop."
            else:
                text = result.text or "I wasn't able to finish this."

        except Exception:

            logger.exception("Wrap-up LLM call failed.")
            text = "I ran into trouble partway through and had to stop."

        self._core.history.append({"role": "assistant", "content": text})
        yield ("token", text)

    # =====================================================
    # LLM Call (non-streaming)
    # =====================================================

    def _call_llm(self) -> ChatResult:
        """Non-streaming path, used by process(). Returns a canonical
        ChatResult so this method is provider-independent like the rest."""

        messages = self._build_messages()
        plan = plan_request(messages, OLLAMA_TOOLS, self._capabilities)
        if not plan.fits:
            return ChatResult(text=plan.error.human(), error=plan.error)
        return self._brain.complete(plan.messages, plan.tools)

    # =====================================================
    # Response Handling
    # =====================================================

    def _handle_response(
        self,
        response: ChatResult,
        confirm_callback: Callable[[str], bool] | None,
        depth: int = 0,
    ) -> str:

        if response.error is not None:
            text = response.error.human()
            self._core.history.append({"role": "assistant", "content": text})
            return text

        tool_calls = response.tool_calls or []

        if not tool_calls:
            text = response.text or ""
            self._core.history.append({"role": "assistant", "content": text})
            return text

        self._core.history.append({
            "role": "assistant",
            "content": response.text or "",
            "tool_calls": [
                {"id": tc.call_id, "function": {"name": tc.name, "arguments": tc.arguments}}
                for tc in tool_calls
            ],
        })

        for tc in tool_calls:

            # Canonical already — normalised at the provider boundary.
            name = tc.name
            args = tc.arguments or {}

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

        # Checked before anything runs, so a malformed call fails with a
        # message the model can act on instead of a bare "Validation failed."
        problem = check_arguments(function_name, args)
        if problem:
            logger.warning("Rejected call: %s", problem)
            return {"status": "error", "error": problem, "retry_safe": True}

        if function_name in MEMORY_TOOLS:
            return self._execute_memory_tool(function_name, args)

        if function_name in _SPECIAL_TOOLS:
            if function_name == "calculate":
                from tools.compute.calculator import calculate

                return calculate(str(args.get("expression", "")))
            if function_name == "see_screen":
                return self._execute_vision(args)
            if function_name == "read_document":
                return self._execute_read_document(args)
            if function_name == "search_files":
                return self._execute_search_files(args)
            return self._execute_spreadsheet(function_name, args)

        # These return structured evidence — exit codes, diffs, line numbers,
        # process state — that the legacy ToolResult wrapper flattens into a
        # single "output" string. They're dispatched directly so that detail
        # reaches the model intact, which is the whole point of them.
        if function_name in _DIRECT_TOOLS:
            return self._execute_direct_tool(function_name, args)

        dispatch = DISPATCH.get(function_name)

        if not dispatch:
            logger.error("Unknown function: %s", function_name)
            # Canonical shape like every other failure: a model naming a tool
            # that does not exist is ordinary misbehaviour, and the result it
            # gets back must be readable in the same way as any other error.
            return {
                "status": "error",
                "error": (
                    f"Unknown function: {function_name}. It is not one of the "
                    "tools available to you."
                ),
                "retry_safe": True,
            }

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

                # ToolExecutor already flattened any exception to a string, so
                # the enrichment has to happen here rather than in the except
                # block below — a bare "[Errno 2] No such file" tells the model
                # nothing about what it should have used instead.
                return {
                    "status": "error",
                    "error": _explain_error_text(
                        result.error or "Tool execution failed", args
                    ),
                }

        except Exception as exc:

            logger.exception("Tool execution error: %s", exc)

            return {"status": "error", "error": _explain_exception(exc, args)}

    def _execute_send_email(self, args: dict) -> dict:
        """Send mail, then confirm it from the mailbox rather than from the id.

        A send call returning an id proves the request was accepted, not that
        the message carries the recipient and attachment intended. So the
        result reports what the mailbox actually holds -- and if the readback
        disagrees with what was asked for, that disagreement reaches the model
        instead of a bare success.
        """
        from tools.email.gmail_client import GmailAuthError, GmailClient

        to = str(args.get("to") or "").strip()
        subject = str(args.get("subject") or "")
        body = str(args.get("body") or "")
        attachments = [str(a) for a in (args.get("attachments") or [])]

        if not to:
            return {"status": "error", "error": "No recipient given.", "retry_safe": True}

        client = GmailClient()
        try:
            message_id = client.send_email(to, subject, body, attachments)
        except GmailAuthError as exc:
            # The remedy belongs to the user; say so plainly rather than
            # letting the model retry a call that cannot succeed.
            return {"status": "error", "error": str(exc), "retry_safe": False}
        except FileNotFoundError as exc:
            return {"status": "error", "error": str(exc), "retry_safe": True}
        except Exception as exc:
            logger.exception("Sending mail failed")
            return {"status": "error", "error": f"Could not send: {exc}", "retry_safe": True}

        try:
            sent = client.describe_sent(message_id)
        except Exception as exc:
            return {
                "status": "success",
                "result": (
                    f"Sent (id {message_id}), but the message could not be read "
                    f"back to verify it: {exc}"
                ),
            }

        wanted = {Path(a).name for a in attachments}
        got = set(sent.get("attachments") or [])
        missing = sorted(wanted - got)

        return {
            "status": "success",
            "result": (
                f"Sent and verified in the mailbox. "
                f"to={sent['to']!r} subject={sent['subject']!r} "
                f"attachments={sent['attachments']} in_sent={sent['in_sent']}"
                + (f" WARNING: expected attachments missing: {missing}" if missing else "")
            ),
            "message_id": message_id,
            "verified": sent,
        }

    def _execute_computer_tool(self, function_name: str, args: dict) -> dict:
        """Operate the machine through the platform adapter.

        Nothing here knows about macOS. The session resolves element
        references and the adapter for whatever platform this is does the
        work, so a Windows adapter would drop in without touching this.
        """
        from computer.session import SESSION

        if function_name == "see_ui":
            return SESSION.observe(app=args.get("app"), limit=int(args.get("limit") or 60))
        if function_name == "click_element":
            return SESSION.click(
                ref=args.get("ref"),
                x=args.get("x"), y=args.get("y"),
                button=str(args.get("button") or "left"),
                count=int(args.get("count") or 1),
            )
        if function_name == "type_text":
            return SESSION.type_text(str(args.get("text") or ""))
        if function_name == "press_keys":
            return SESSION.press_keys(str(args.get("key") or ""), args.get("modifiers") or [])
        if function_name == "scroll_ui":
            return SESSION.scroll(
                dy=int(args.get("dy") or 0), dx=int(args.get("dx") or 0), ref=args.get("ref"),
            )
        if function_name == "list_windows":
            return SESSION.list_windows()
        if function_name == "focus_app":
            return SESSION.focus_app(str(args.get("name") or ""))
        return {"status": "error", "error": f"Unhandled computer tool: {function_name}"}

    def _execute_direct_tool(self, function_name: str, args: dict) -> dict:
        """
        Runs the tools whose value is in their structured result, and returns
        that result as-is. No reshaping into success/error strings: the model
        decides what a non-zero exit code or an unmatched edit means, and it
        can only do that if it actually sees them.
        """
        from tools.filesystem import edits as file_edits
        from tools.project import inspect as project_inspect
        from tools.terminal import actions as terminal_actions

        if function_name in _COMPUTER_TOOLS:
            return self._execute_computer_tool(function_name, args)

        if function_name == "send_email":
            return self._execute_send_email(args)

        try:
            if function_name == "run_command":
                result = terminal_actions.run(
                    command=args.get("command", ""),
                    cwd=args.get("cwd"),
                    timeout=int(args.get("timeout") or terminal_actions.DEFAULT_TIMEOUT),
                )
                return self._shape_command_result(result)

            if function_name == "run_background":
                result = terminal_actions.run_background(
                    command=args.get("command", ""),
                    cwd=args.get("cwd"),
                )
                if result.get("running"):
                    return {
                        "status": "success",
                        "result": (
                            f"Started (pid {result['pid']}) and still running. "
                            "Use list_processes or process_output to check on it."
                        ),
                        **result,
                    }
                return {
                    "status": "error",
                    "error": (
                        f"The process exited immediately with code "
                        f"{result.get('exit_code')}."
                    ),
                    **result,
                }

            if function_name == "list_processes":
                return {"status": "success", **terminal_actions.list_processes()}

            if function_name == "process_output":
                result = terminal_actions.process_output(int(args.get("pid", 0)))
                if "error" in result:
                    return {"status": "error", **result}
                return {"status": "success", **result}

            if function_name == "kill_process":
                result = terminal_actions.kill_process(int(args.get("pid", 0)))
                if "error" in result:
                    return {"status": "error", **result}
                return {"status": "success", **result}

            if function_name == "read_lines":
                return file_edits.read_lines(
                    path=args.get("path", ""),
                    offset=int(args.get("offset") or 1),
                    limit=int(args.get("limit") or 400),
                )

            if function_name == "edit_file":
                return file_edits.edit_file(
                    path=args.get("path", ""),
                    old_text=args.get("old_text", ""),
                    new_text=args.get("new_text", ""),
                    expect_count=args.get("expect_count"),
                )

            if function_name == "multi_edit":
                return file_edits.multi_edit(
                    path=args.get("path", ""),
                    edits=args.get("edits") or [],
                )

            if function_name == "project_overview":
                return project_inspect.project_overview(path=args.get("path") or ".")

            if function_name == "project_tree":
                return project_inspect.project_tree(
                    path=args.get("path") or ".",
                    max_depth=int(args.get("max_depth") or 3),
                )

            if function_name in ("check_url", "check_port", "check_syntax"):
                from tools.verify import checks

                if function_name == "check_url":
                    return checks.check_url(
                        url=args.get("url", ""),
                        expect=args.get("expect", "") or "",
                    )
                if function_name == "check_port":
                    return checks.check_port(
                        port=args.get("port", 0), host=args.get("host") or "127.0.0.1"
                    )
                return checks.check_syntax(path=args.get("path", ""))

            if function_name == "search_code":
                return project_inspect.search_code(
                    query=args.get("query", ""),
                    path=args.get("path") or ".",
                    file_glob=args.get("file_glob") or "",
                    regex=bool(args.get("regex")),
                )

        except Exception as exc:
            logger.exception("Direct tool failed: %s", function_name)
            return {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "tool": function_name,
            }

        return {"status": "error", "error": f"Unhandled tool: {function_name}"}

    @staticmethod
    def _shape_command_result(result: dict) -> dict:
        """
        A command that exits non-zero is reported as a real outcome with all
        of its output, not as a bare failure. Tests failing, a build erroring,
        a grep finding nothing — these are informative results the model needs
        the detail of, and previously all of it was discarded.
        """
        if result.get("timed_out"):
            return {
                "status": "error",
                "error": (
                    f"Command was still running after "
                    f"{result.get('timeout_seconds')}s and was stopped. If it is "
                    "a server or watcher, start it with run_background instead."
                ),
                **result,
            }

        exit_code = result.get("exit_code")

        if exit_code == 0:
            stdout = result.get("stdout", "")
            return {
                "status": "success",
                "result": stdout if stdout.strip() else "Command finished with no output.",
                **result,
            }

        return {
            "status": "command_failed",
            # Worded to read as a failure to the Activity log too, which
            # classifies a step by its status text — a command that exited
            # non-zero should not be recorded as having succeeded.
            "error": (
                f"Command failed with exit code {exit_code}. Its full output is "
                "included here — read it to decide what to do next."
            ),
            **result,
        }

    # =====================================================
    # Documents
    # =====================================================

    def _execute_read_document(self, args: dict) -> dict:
        try:
            from tools.filesystem.document_reader import (
                DocumentUnreadable,
                read_document,
            )
            path = args.get("path", "")
            if not path:
                return {"status": "error", "error": "No file path provided."}
            text = read_document(path)
            logger.info("Document read: %s (%d chars)", path, len(text))
            return {"status": "success", "result": text}
        except FileNotFoundError as exc:
            return {"status": "error", "error": str(exc), "retry_safe": True}
        except DocumentUnreadable as exc:
            # The file is there and the path is right; the format or the file
            # itself is the problem, so retrying the same call cannot help.
            return {"status": "error", "error": str(exc), "retry_safe": False}
        except Exception as exc:
            logger.exception("Document read failed: %s", exc)
            return {
                "status": "error",
                "error": f"Could not read {args.get('path', 'the document')}: {exc}",
                "retry_safe": False,
            }

    def _execute_search_files(self, args: dict) -> dict:
        """Find files by name.

        This used to do content search too, by running `grep -r` from the
        user's Desktop with a 15 second timeout. On any real machine that is a
        guaranteed timeout -- measured here against a 7.3 GB Desktop -- and it
        duplicated search_code, which does content search properly with
        ripgrep and returns line numbers.

        Two tools doing the same job badly is worse than one doing it well, so
        this now does the thing search_code cannot: locate files by name.
        Content searches are directed to search_code instead.
        """
        import subprocess

        from tools.filesystem.path_utils import resolve_path

        query = (args.get("query") or "").strip()
        if not query:
            return {"status": "error", "error": "No filename to search for."}

        where = args.get("path")
        root = resolve_path(where) if where else Path.home()
        if not root.exists():
            return {"status": "error", "error": f"No such directory: {root}"}

        file_type = (args.get("file_type") or "").lstrip(".")
        pattern = query if any(c in query for c in "*?[") else f"*{query}*"
        if file_type:
            pattern = f"{pattern}.{file_type}" if not pattern.endswith(f".{file_type}") else pattern

        # Prune the directories that make a home-directory search hopeless.
        skip = ("Library", "node_modules", ".git", "venv", ".venv", "__pycache__",
                ".Trash", "Applications", ".cache")
        cmd = ["find", str(root)]
        for name in skip:
            cmd += ["-name", name, "-prune", "-o"]
        cmd += ["-iname", pattern, "-type", "f", "-print"]

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": (
                f"Searching {root} for {pattern!r} took too long. Give a narrower "
                "path, or use search_code if you are looking for text inside files."
            )}

        found = [line for line in (proc.stdout or "").splitlines() if line.strip()]
        if not found:
            return {"status": "success", "result": (
                f"No file matching {pattern!r} under {root}. If you meant to "
                "search inside files rather than for a filename, use search_code."
            )}

        shown = found[:50]
        more = f"\n... and {len(found) - 50} more" if len(found) > 50 else ""
        return {
            "status": "success",
            "match_count": len(found),
            "result": "\n".join(shown) + more,
        }

    def _execute_vision(self, args: dict) -> dict:

        # Vision may come from the brain itself or from a separate model.
        # Either way, if nothing configured can see, say so plainly instead
        # of attempting the call and surfacing a backend error.
        if not self._vision_available():
            return {
                "status": "error",
                "error": (
                    f"{self._brain_capabilities().model} can't look at images, and no "
                    "separate vision model is configured. Set one, or switch to "
                    "a vision-capable model, and I'll be able to see the screen."
                ),
            }

        try:
            vision = Vision()
            # Two budgets, not one. Operating an interface needs a short list
            # of controls; answering "what's on my screen" needs prose. Vision
            # latency is almost entirely generation, so asking for the right
            # one is the difference between roughly three seconds and ten.
            if str(args.get("purpose") or "").strip().lower() == "controls":
                description = vision.read_controls()
            else:
                description = vision.describe_screen()

            logger.info("Vision result: %s", description[:120])

            # Caching the description for situation freshness is bookkeeping,
            # not the result. It used to sit inside the same try as the vision
            # call itself, so a failure here discarded a description that had
            # already been obtained successfully — reporting "vision failed"
            # when vision had in fact worked. The observation is what the
            # model asked for; losing it over a cache write is never right.
            if description:
                try:
                    self._core.set_vision(description)
                except Exception:
                    logger.exception("Could not cache the vision result.")

            return {
                "status": "success",
                "result": description or "I could see your screen but couldn't describe it.",
            }

        except Exception as exc:
            logger.exception("Vision failed: %s", exc)

            msg = str(exc)
            if "screen capture" in msg.lower() or "permission" in msg.lower():
                return {
                    "status": "error",
                    "error": "Screen capture failed. Check that screen recording permission is granted in System Settings → Privacy & Security.",
                }

            # Wording comes from the provider, so it stays accurate whichever
            # backend is in use — the runtime never names one itself.
            try:
                translated = self._vision_brain().translate_error(exc)
                if translated.kind in ("unavailable", "timeout", "protocol"):
                    return {"status": "error", "error": translated.human()}
            except Exception:
                pass
            return {"status": "error", "error": f"Vision failed: {msg}"}

    def _brain_capabilities(self):
        """Capabilities, resolved on demand.

        Lazy rather than read straight off an attribute so that nothing here
        depends on construction order — the vision path is reachable from
        contexts that never ran __init__.
        """
        caps = getattr(self, "_capabilities", None)
        if caps is None:
            caps = get_provider().capabilities()
            self._capabilities = caps
        return caps

    def _vision_brain(self):
        """The brain used for images — the same one when it can see, a
        separately configured model when it can't."""
        if self._brain_capabilities().can("vision"):
            return getattr(self, "_brain", None) or get_provider()
        if getattr(self, "_vision_provider", None) is None:
            self._vision_provider = get_provider(model=OLLAMA_VISION_MODEL)
        return self._vision_provider

    def _vision_available(self) -> bool:
        try:
            return self._vision_brain().capabilities().can("vision")
        except Exception:
            return False

    # =====================================================
    # Helpers
    # =====================================================

    def _build_messages(self) -> list[dict]:
        last_user = ""
        for msg in reversed(self._core.history):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break

        memories = (
            memory_store.auto_recall(last_user, project_id=self._core.project_id)
            if last_user else []
        )

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

    def _execute_spreadsheet(self, name: str, args: dict) -> dict:
        """Cell-level spreadsheet work.

        Returned as-is like the other structured tools: the grid, the
        formulas, and the note about uncalculated values are exactly what the
        model needs to avoid inventing a total, and flattening them into a
        sentence would throw that away.
        """
        from tools.filesystem import spreadsheet

        try:
            if name == "read_spreadsheet":
                return spreadsheet.read_sheet(
                    path=args.get("path", ""),
                    sheet=args.get("sheet") or None,
                )

            cells = args.get("cells")
            if not isinstance(cells, dict):
                return {
                    "status": "error",
                    "retry_safe": True,
                    "error": (
                        "cells must be an object keyed by cell reference, for "
                        'example {"B6": 4820, "C6": "=SUM(C2:C5)"}. '
                        f"Received: {type(cells).__name__}."
                    ),
                }
            return spreadsheet.write_cells(
                path=args.get("path", ""),
                cells=cells,
                sheet=args.get("sheet") or None,
            )

        except FileNotFoundError as exc:
            # The path is wrong and a different path may work.
            return {"status": "error", "error": str(exc), "retry_safe": True}
        except spreadsheet.SpreadsheetError as exc:
            # The file or the request is the problem. Its messages already say
            # what to do instead, so they are passed through unchanged.
            return {"status": "error", "error": str(exc), "retry_safe": True}
        except Exception as exc:
            logger.exception("Spreadsheet tool failed: %s", exc)
            return {
                "status": "error",
                "error": f"{args.get('path', 'the spreadsheet')} could not be "
                         f"processed: {exc}",
            }

    def _execute_memory_tool(self, name: str, args: dict) -> dict:
        if name == "remember":
            return memory_store.remember(
                content=args.get("content", ""),
                category=args.get("category", "fact"),
                project_id=self._core.project_id,
            )
        if name == "recall_memory":
            return memory_store.recall(
                query=args.get("query", ""),
                category=args.get("category", ""),
                project_id=self._core.project_id,
            )
        if name == "forget_memory":
            # Deliberately not project-scoped: if the user says "forget X",
            # a wrong fact should go away regardless of which project it was
            # attached to — scoping deletion adds a real chance of "I forgot
            # it" being untrue from inside a different project.
            return memory_store.forget(
                query=args.get("query", ""),
            )
        return {"status": "error", "error": f"Unknown memory tool: {name}"}


def _explain_exception(exc: Exception, args: dict) -> str:
    return _explain_error_text(str(exc), args, is_missing=isinstance(
        exc, (FileNotFoundError, NotADirectoryError)))


def _explain_error_text(message: str, args: dict, is_missing: bool | None = None) -> str:
    """
    Turns a raw not-found error into something a model can act on.

    "[Errno 2] No such file or directory: '/long/path'" states the problem but
    withholds the one fact needed to fix it: what actually is there. Naming
    the nearest existing directory and its contents turns a dead end into a
    correctable mistake, without deciding anything on the model's behalf.
    """
    if is_missing is None:
        is_missing = (
            "No such file or directory" in message
            or "Not a directory" in message
        )
    if not is_missing:
        return message

    raw = args.get("path") or args.get("source") or ""
    if not raw:
        return message

    try:
        from tools.filesystem.path_utils import resolve_path
        target = resolve_path(str(raw))
    except Exception:
        return message

    parent = target.parent
    if not parent.is_dir():
        return (
            f"{target} does not exist, and neither does its parent directory "
            f"{parent}. Check the path."
        )

    try:
        entries = sorted(p.name + ("/" if p.is_dir() else "") for p in parent.iterdir())
    except OSError:
        return f"{target} does not exist."

    if not entries:
        return f"{target} does not exist. {parent} is empty."

    shown = entries[:40]
    more = f" (and {len(entries) - len(shown)} more)" if len(entries) > len(shown) else ""
    return (
        f"{target} does not exist. {parent} contains: "
        f"{', '.join(shown)}{more}."
    )


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
