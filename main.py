from config.settings import APP_NAME
from logs.logger import logger
from brain.mike import Mike


def main():
    print("=" * 50)
    logger.info(f"Starting {APP_NAME}")
    print("=" * 50)

    try:
        mike = Mike()
        mike.run()

    except KeyboardInterrupt:
        logger.info("Mike stopped by user (Ctrl+C).")
        print("\n👋 Goodbye!")

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print("\n❌ Mike encountered a fatal error.")


if __name__ == "__main__":
    main()