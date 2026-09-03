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

import unittest
from unittest.mock import MagicMock, patch

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

    @patch("vision.analyzer.ollama.Client")
    def test_uses_local_ollama(self, mock_client_cls):
        analyzer = VisionAnalyzer()
        self.assertIsNotNone(analyzer._client)
        mock_client_cls.assert_called_once()

    @patch("vision.analyzer.ollama.Client")
    def test_analyze_sends_image_path(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.chat.return_value = MagicMock(
            message=MagicMock(content="A desktop with a browser open")
        )
        mock_client_cls.return_value = mock_client

        analyzer = VisionAnalyzer()
        result = analyzer.analyze("/tmp/test.png", "Describe the screen")

        call_args = mock_client.chat.call_args
        msgs = call_args.kwargs.get("messages") or call_args[1].get("messages")
        self.assertEqual(msgs[0]["images"], ["/tmp/test.png"])
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
        desc = tool["function"]["description"]
        self.assertIn("explicitly", desc.lower())
        self.assertNotIn("automatic", desc.lower())


if __name__ == "__main__":
    unittest.main()
