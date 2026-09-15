import logging

from hostplatform.storage import log_dir

_LOG_FILE = log_dir() / "mike.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(str(_LOG_FILE)),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Mike")