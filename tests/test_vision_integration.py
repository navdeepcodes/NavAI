"""Tests for the vision feature integration.

Tests cover:
1. see_screen tool declaration exists and is wired
2. VisionAnalyzer uses local Ollama only
3. _execute_vision returns proper result structure
4. _execute_vision handles errors with human-readable messages
5. Normal conversation does NOT invoke see_screen
6. friendly_tool_name and action card parsing
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests import _isolate  # noqa: F401,E402 — must run before any brain/config import

from brain.core_tools import (
    DISPATCH,
    OLLAMA_TOOLS,
    friendly_tool_name,
)
from ui.widgets.conversation.tool_bubble import _parse_action
from vision.analyzer import VisionAnalyzer


class TestToolDeclaration(unittest.TestCase):

    def test_see_screen_in_dispatch(self):
        self.assertIn("see_screen", DISPATCH)
        self.assertEqual(DISPATCH["see_screen"], ("vision", "see_screen"))

    def test_see_screen_in_ollama_tools(self):
        names = [t["function"]["name"] for t in OLLAMA_TOOLS]
        self.assertIn("see_screen", names)

    def test_see_screen_has_no_required_params(self):
        tool = next(
            t for t in OLLAMA_TOOLS
            if t["function"]["name"] == "see_screen"
        )
        params = tool["function"]["parameters"]
        self.assertEqual(params.get("required", []), [])

    def test_friendly_name(self):
        self.assertEqual(
            friendly_tool_name("see_screen", {}),
            "Looking at your screen",
        )


class TestActionCardParsing(unittest.TestCase):

    def test_vision_icon(self):
        icon, label, detail = _parse_action("Looking at your screen")
        self.assertEqual(icon, "◉")
        self.assertEqual(label, "Looking at your screen")
        self.assertEqual(detail, "")


class TestVisionAnalyzerLocal(unittest.TestCase):

    # VisionAnalyzer no longer owns a model client — images go through the
    # provider boundary like every other model call. These tests keep their
    # original guarantees (vision stays local, and the image path actually
    # reaches the model) and assert them against the new path.

    def test_uses_a_local_provider(self):
        analyzer = VisionAnalyzer()
        caps = analyzer._brain.capabilities()
        self.assertEqual(caps.provider, "ollama", "vision must stay local")
        self.assertTrue(caps.can("vision"), "the configured vision model must see")

    def test_analyze_sends_image_path_to_the_model(self):
        # A provider of this test's own, so mutating its client cannot leak
        # into the shared cached provider other tests rely on.
        from brain.providers.ollama_provider import OllamaProvider
        from config.ollama import OLLAMA_HOST, OLLAMA_VISION_MODEL

        provider = OllamaProvider(model=OLLAMA_VISION_MODEL, host=OLLAMA_HOST)

        seen = {}

        def fake_chat(**kwargs):
            seen.update(kwargs)
            return MagicMock(
                message=MagicMock(content="A desktop with a browser open")
            )

        provider._client = MagicMock(chat=fake_chat)
        analyzer = VisionAnalyzer(provider=provider)
        result = analyzer.analyze("/tmp/test.png", "Describe the screen")

        self.assertEqual(seen["messages"][0]["images"], ["/tmp/test.png"])
        self.assertEqual(result, "A desktop with a browser open")


class TestExecuteVision(unittest.TestCase):

    @patch("brain.core_runtime.Vision")
    def test_success_returns_description(self, mock_vision_cls):
        mock_vision = MagicMock()
        mock_vision.describe_screen.return_value = "Safari browser showing google.com"
        mock_vision_cls.return_value = mock_vision

        from brain.core_runtime import CoreRuntime
        runtime = CoreRuntime.__new__(CoreRuntime)
        result = runtime._execute_vision({})

        self.assertEqual(result["status"], "success")
        self.assertIn("Safari", result["result"])

    @patch("brain.core_runtime.Vision")
    def test_model_not_found_error(self, mock_vision_cls):
        mock_vision = MagicMock()
        mock_vision.describe_screen.side_effect = RuntimeError(
            "Vision model 'qwen2.5vl:3b' is not found"
        )
        mock_vision_cls.return_value = mock_vision

        from brain.core_runtime import CoreRuntime
        runtime = CoreRuntime.__new__(CoreRuntime)
        result = runtime._execute_vision({})

        self.assertEqual(result["status"], "error")
        self.assertIn("ollama pull", result["error"])

    @patch("brain.core_runtime.Vision")
    def test_connection_refused_error(self, mock_vision_cls):
        mock_vision = MagicMock()
        mock_vision.describe_screen.side_effect = ConnectionError(
            "Connection refused"
        )
        mock_vision_cls.return_value = mock_vision

        from brain.core_runtime import CoreRuntime
        runtime = CoreRuntime.__new__(CoreRuntime)
        result = runtime._execute_vision({})

        self.assertEqual(result["status"], "error")
        self.assertIn("Ollama", result["error"])

    @patch("brain.core_runtime.Vision")
    def test_permission_error(self, mock_vision_cls):
        mock_vision = MagicMock()
        mock_vision.describe_screen.side_effect = RuntimeError(
            "Screen capture permission denied"
        )
        mock_vision_cls.return_value = mock_vision

        from brain.core_runtime import CoreRuntime
        runtime = CoreRuntime.__new__(CoreRuntime)
        result = runtime._execute_vision({})

        self.assertEqual(result["status"], "error")
        self.assertIn("System Settings", result["error"])


class TestNormalConversationNoVision(unittest.TestCase):

    def test_casual_message_no_see_screen_tool(self):
        """Verify that see_screen requires explicit user request via description."""
        tool = next(
            t for t in OLLAMA_TOOLS
            if t["function"]["name"] == "see_screen"
        )
        desc = tool["function"]["description"].lower()
        # The guarantee here changed deliberately with the computer-control
        # work, and this test changed with it rather than being deleted.
        #
        # Before: screen capture happened only when the user asked for it.
        # Now: vision is also the fallback for surfaces the accessibility tree
        # cannot describe -- canvas, drawn content, apps that expose no tree --
        # which necessarily means Mike may capture the screen on its own
        # initiative during a computer-use task.
        #
        # What still must hold is that it is never the casual or default way
        # to look at an application. see_ui reads the same window as text in
        # ~0.04s against ~3-10s for vision, so the declaration has to steer
        # the model there first and describe capture as a fallback. That is
        # the property worth protecting, and it is what is asserted.
        self.assertIn(
            "the user asks", desc,
            "a direct user request must remain a listed reason to look",
        )
        self.assertIn(
            "see_ui", desc,
            "the declaration must point at the cheaper semantic path first",
        )
        self.assertIn(
            "fallback", desc,
            "vision must be described as a fallback, not the default",
        )
        self.assertNotIn("automatic", desc)


if __name__ == "__main__":
    unittest.main()
