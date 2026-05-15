# workers/trade_worker.py
import time
from infra import redis_bus as rbus
from services.market_service import update_excursion

def run():
    print("🚀 Trade Worker Online")
    while True:
        # Check both the job queue and the main ticker updates
        job = rbus.queue_pop("job_queue", timeout=1)
        if job and job.get("type") == "trade_update":
            update_excursion(job["token"], job["ltp"])
        
        # Self-correction: check if any active trades need LTP sync from Redis
        time.sleep(0.1)

if __name__ == "__main__":
    run()
