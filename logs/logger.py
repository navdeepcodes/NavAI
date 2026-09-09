import logging

from hostplatform import storage

# Used to be logs/mike.log, relative to whatever directory the process was
# launched from — the same class of bug as the OAuth token file (see
# hostplatform/storage.py). An installed app is frequently launched from a
# directory it cannot write to, and even when it can, the log ended up
# scattered into whatever folder happened to be current at launch rather than
# living beside Mike's other persistent data.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(str(storage.log_path())),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Mike")
