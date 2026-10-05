import logging
import sys
from app.scheduler.service import JobScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

def main():
    scheduler = JobScheduler()
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nStopping scheduler...")
        scheduler.stop()

if __name__ == "__main__":
    main()
