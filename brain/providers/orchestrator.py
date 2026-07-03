from logs.logger import logger

from brain.providers.task_type import TaskType


class AIOrchestrator:

    # ---------------------------------------------------------

    def __init__(self, providers):

        self.providers = providers

    # ---------------------------------------------------------

    def choose(self, request):

        if not self.providers:

            raise RuntimeError(
                "No providers available."
            )

        ranked = []

        for provider in self.providers:

            score = self._score(
                provider,
                request
            )

            if score >= 0:

                ranked.append(
                    (score, provider)
                )

        if not ranked:

            raise RuntimeError(
                "No provider satisfies the requested capabilities."
            )

        ranked.sort(
            key=lambda item: item[0],
            reverse=True
        )

        logger.info("Provider ranking")

        for score, provider in ranked:

            logger.info(
                f"{provider.name:<12} {score}"
            )

        best = ranked[0][1]

        logger.info(
            f"Selected Provider: {best.name}"
        )

        return best

    # ---------------------------------------------------------

    def _score(
        self,
        provider,
        request
    ):

        cap = provider.capability

        score = 0

        # ---------------------------------
        # Hard requirements
        # ---------------------------------

        if request.requires_local and not cap.local:
            return -1

        if request.requires_vision and not cap.vision:
            return -1

        if request.requires_tools and not cap.tools:
            return -1

        if request.streaming and not cap.streaming:
            return -1

        # ---------------------------------
        # Task-specific scoring
        # ---------------------------------

        if request.task == TaskType.CHAT:

            score += cap.speed_score * 2
            score += cap.reasoning_score

        elif request.task == TaskType.CODING:

            score += cap.coding_score * 3
            score += cap.reasoning_score

        elif request.task == TaskType.REASONING:

            score += cap.reasoning_score * 3

        elif request.task == TaskType.VISION:

            score += cap.reasoning_score * 2

        elif request.task == TaskType.PLANNING:

            score += cap.reasoning_score * 3
            score += cap.context_window // 50000

        elif request.task == TaskType.TOOL:

            score += 20

        elif request.task == TaskType.MEMORY:

            score += cap.context_window // 25000

        # ---------------------------------
        # General capability bonuses
        # ---------------------------------

        score += cap.context_window // 10000

        score += cap.privacy_score

        score += cap.speed_score

        score -= cap.cost_score

        return score

    # ---------------------------------------------------------

    def rank(
        self,
        request
    ):

        ranking = []

        for provider in self.providers:

            score = self._score(
                provider,
                request
            )

            ranking.append(
                (provider, score)
            )

        ranking.sort(
            key=lambda item: item[1],
            reverse=True
        )

        return ranking