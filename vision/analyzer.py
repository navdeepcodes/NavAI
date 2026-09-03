from __future__ import annotations

import ollama

from config.ollama import (
    OLLAMA_HOST,
    OLLAMA_VISION_MODEL,
    VISION_NUM_PREDICT,
    VISION_TEMPERATURE,
)
from logs.logger import logger


class VisionAnalyzer:
    """Analyzes images using the local Ollama vision model."""

    def __init__(self) -> None:
        self._client = ollama.Client(host=OLLAMA_HOST)
        self._model = OLLAMA_VISION_MODEL
        logger.info("VisionAnalyzer ready (model=%s).", self._model)

    def analyze(
        self,
        image_path: str,
        prompt: str = "Describe everything visible on this screen.",
    ) -> str:
        logger.info("Vision: analyzing %s", image_path)

        try:
            response = self._client.chat(
                model=self._model,
                messages=[{
                    "role": "user",
                    "content": prompt,
                    "images": [image_path],
                }],
                think=False,
                options={
                    "temperature": VISION_TEMPERATURE,
                    "num_predict": VISION_NUM_PREDICT,
                },
            )

            text = response.message.content or ""
            logger.info("Vision result: %s", text[:120])
            return text

        except ollama.ResponseError as exc:
            logger.error("Vision model error: %s", exc)
            if "not found" in str(exc).lower():
                raise RuntimeError(
                    f"Vision model '{self._model}' is not installed. "
                    f"Run: ollama pull {self._model}"
                ) from exc
            raise

        except Exception as exc:
            logger.exception("Vision analysis failed: %s", exc)
            raise
