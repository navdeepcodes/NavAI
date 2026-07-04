from __future__ import annotations

from brain.provider import get_provider

from brain.intelligence.analysis import CognitiveAnalysis
from brain.intelligence.analysis_parser import AnalysisParser
from brain.intelligence.analysis_prompt import ANALYSIS_PROMPT


class Analyzer:
    """
    Mike's Cognitive Analyzer.

    The Analyzer performs semantic understanding of the
    user's message before any reasoning or planning occurs.

    Responsibilities

    - Understand intent
    - Detect emotion
    - Extract entities
    - Detect urgency
    - Determine if tools are required

    It NEVER plans or executes actions.
    """

    # ---------------------------------------------------------

    def __init__(self):

        self.parser = AnalysisParser()

    # ---------------------------------------------------------

    def analyze(
        self,
        message: str,
    ) -> CognitiveAnalysis | None:

        provider = get_provider()

        prompt = f"""

{ANALYSIS_PROMPT}

User

{message}

JSON

"""

        result = provider.complete(

            prompt

        )

        return self.parser.parse(

            result

        )