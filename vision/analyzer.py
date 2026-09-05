from __future__ import annotations

from config.ollama import OLLAMA_VISION_MODEL
from logs.logger import logger


class VisionAnalyzer:
    """Describes an image using whichever brain is configured to see.

    Deliberately has no model client of its own. Vision may be served by the
    same model that powers Mike's brain or by a separate one, and either may
    live behind a different backend later — all of which is the provider
    boundary's business, not this class's.
    """

    def __init__(self, model: str | None = None, provider=None) -> None:
        from brain.providers import get_provider

        self._model = model or OLLAMA_VISION_MODEL
        # An explicit provider can be supplied (tests, or a caller that has
        # already resolved one). Otherwise the shared configured provider is
        # used — which callers must not mutate, since it is cached.
        self._brain = provider or get_provider(model=self._model)
        logger.info("VisionAnalyzer ready (model=%s).", self._model)

    def can_see(self) -> bool:
        """Whether the configured vision model can actually accept images."""
        try:
            return self._brain.capabilities().can("vision")
        except Exception:
            return False

    def analyze(
        self,
        image_path: str,
        prompt: str = "Describe everything visible on this screen.",
        max_tokens: int | None = None,
    ) -> str:
        logger.info("Vision: analyzing %s", image_path)

        text, error = self._brain.describe_image(image_path, prompt, max_tokens)

        if error is not None:
            # Raised rather than returned because callers already treat vision
            # failure as an exception; the message is the provider's, so it
            # names the right backend and the right remedy.
            logger.error("Vision failed (%s): %s", error.kind, error.detail)
            raise RuntimeError(error.human())

        logger.info("Vision result: %s", text[:120])
        return text
