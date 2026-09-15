import tempfile

from PIL import Image

from config.ollama import VISION_RESOLUTION
from hostplatform.capture import capture_raw
from logs.logger import logger


class Screenshot:

    def capture(self) -> str:
        raw = str(capture_raw())

        img = Image.open(raw)
        ratio = VISION_RESOLUTION / max(img.size)

        if ratio < 1.0:
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        out = tempfile.mktemp(suffix=".png")
        img.save(out)
        logger.info("Screenshot: %dx%d → %s", img.width, img.height, out)

        import os
        try:
            os.unlink(raw)
        except OSError:
            pass

        return out
