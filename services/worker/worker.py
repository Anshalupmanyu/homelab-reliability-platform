
import json
import time
import signal
import gc
import redis

from datetime import datetime, timezone
from redis_client import redis_client
from logging_config import logger


# --------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------

QUEUE_NAME = "jobs_queue"

MEMORY_LIMIT_MB = 32

running = True


# --------------------------------------------------
# 2. TASK FUNCTIONS
# --------------------------------------------------

def compute(duration: int, job_id: str):
    """
    Performs a bounded CPU computation for the
    requested duration.
    """

    logger.info(
        "Compute task started",
        extra={
            "event": "compute_started",
            "job_id": job_id}
    )

    deadline = time.monotonic() + duration

    result = 0

    while time.monotonic() < deadline:
        for i in range(1000):
            result += i * i

    logger.info(
        "Compute task completed",
        extra={
            "event": "compute_completed",
            "job_id": job_id,
            "result": result
        }
    )


def error(duration: int, job_id: str):
    """
    Intentionally raises an exception.
    Used to test failure handling.
    """

    logger.warning(
        "Error task triggered",
        extra={
            "event": "error_task_triggered",
            "job_id": job_id
        }
    )

    raise RuntimeError("Intentional error task failure")


def cpu_spike(duration: int, job_id: str):
    """
    Generates sustained CPU activity for
    the requested duration.
    """

    logger.warning(
        "CPU spike task started",
        extra={
            "event": "cpu_spike_started",
            "job_id": job_id}
    )

    deadline = time.monotonic() + duration

    result = 0

    while time.monotonic() < deadline:
        for i in range(10000):
            result += i * i

    logger.info(
        "CPU spike task completed",
        extra={
            "event": "cpu_spike_completed",
            "job_id": job_id
        }
    )


def memory_leak(duration: int, job_id: str):
    """
    Simulates memory growth.

    Memory is capped at MEMORY_LIMIT_MB and
    released when the task finishes.
    """

    logger.warning(
        "Memory leak simulation started",
        extra={
            "event": "memory_leak_started",
            "job_id": job_id
        }
    )

    memory_chunks = []

    try:

        for _ in range(MEMORY_LIMIT_MB):
            memory_chunks.append(bytearray(1024 * 1024))

        time.sleep(duration)

        logger.info(
            "Memory leak simulation completed",
            extra={
                "event": "memory_leak_completed",
                "job_id": job_id,
                "allocated_mb": MEMORY_LIMIT_MB
            }
        )

    finally:

        memory_chunks.clear()
        gc.collect()


# --------------------------------------------------
# 3. TASK REGISTRY
# --------------------------------------------------

TASKS = {
    "compute": compute,
    "error": error,
    "cpu_spike": cpu_spike,
    "memory_leak": memory_leak
}


# --------------------------------------------------
# 4. JOB PROCESSING
# --------------------------------------------------

def process_job(job_data: dict):

    job_id = job_data["job_id"]
    task_name = job_data["task"]
    duration = int(job_data["duration"])

    redis_key = f"job:{job_id}"

    logger.info(
        "Job received by worker",
        extra={
            "event": "job_received",
            "job_id": job_id,
            "task": task_name
        }
    )

    try:

        # Update job status to running
        redis_client.hset(
            redis_key,
            mapping={
                "status": "processing",
                "started_at": datetime.now(timezone.utc).isoformat()
            }
        )

        logger.info(
            "Job execution started",
            extra={
                "event": "job_started",
                "job_id": job_id,
                "task": task_name
            }
        )

        # Execute the requested task
        task_function = TASKS.get(task_name)

        if task_function is None:
            raise ValueError(f"Unknown task: {task_name}")

        task_function(duration, job_id)

        # Update job status to completed
        redis_client.hset(
            redis_key,
            mapping={
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
        )

        logger.info(
            "Job completed successfully",
            extra={
                "event": "job_completed",
                "job_id": job_id,
                "task": task_name
            }
        )

    except Exception as exc:

        # Update job status to failed
        try:

            redis_client.hset(
                redis_key,
                mapping={
                    "status": "failed",
                    "error": str(exc),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
            )

        except Exception:

            logger.exception(
                "Could not update failed job status",
                extra={
                    "event": "job_status_update_failed",
                    "job_id": job_id
                }
            )

        logger.exception(
            "Job execution failed",
            extra={
                "event": "job_failed",
                "job_id": job_id,
                "task": task_name
            }
        )


# --------------------------------------------------
# 5. GRACEFUL SHUTDOWN
# --------------------------------------------------

def shutdown_handler(signum, frame):

    global running

    logger.info(
        "Worker shutdown requested",
        extra={"event": "worker_shutdown_requested"}
    )

    running = False


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


# --------------------------------------------------
# 6. MAIN WORKER LOOP
# --------------------------------------------------

def start_worker():

    logger.info(
        "Worker started",
        extra={"event": "worker_started"}
    )

    while running:

        try:

            # Wait for a job for up to 5 seconds
            result = redis_client.brpop(
                QUEUE_NAME,
                timeout=5
            )

            # No job arrived
            if result is None:
                continue

            # Extract JSON payload
            queue_name, queue_payload = result

            # Convert JSON string into Python dictionary
            job_data = json.loads(queue_payload)

            # Process the job
            process_job(job_data)

        except json.JSONDecodeError:

            logger.exception(
                "Invalid JSON received from queue",
                extra={"event": "invalid_queue_payload"}
            )

        except redis.RedisError:

            logger.exception(
                "Redis connection error in worker",
                extra={"event": "redis_connection_error"}
            )

            time.sleep(2)

        except Exception:

            logger.exception(
                "Unexpected worker error",
                extra={"event": "worker_unexpected_error"}
            )

    logger.info(
        "Worker stopped",
        extra={"event": "worker_stopped"}
    )


# --------------------------------------------------
# 7. ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":
    start_worker()
