from fastapi import FastAPI, HTTPException
from typing import Literal
import uuid
from pydantic  import BaseModel, Field
from datetime import datetime, timezone
from redis_client import redis_client
from logging_config import logger
import redis
import json


app = FastAPI(title="HomeLab Reliability Platform API")

class JobRequest(BaseModel):
    task: Literal["compute", "error", "cpu_spike", "memory_leak"] = "compute"
    duration: int = Field(default=2, ge=1, le=60)

@app.get("/health")
def read_health():
    try:
        redis_client.ping()

        logger.info(
            "Health check successful",
            extra={
                "event": "health_check",
                "redis_status": "connected"
            }
        )
        return {
            "status" : "ok",
            "redis" : "connected"
        }
    except redis.RedisError:

        logger.exception(
            "Health check failed",
            extra={
                "event": "health_check_failed",
                "redis_status": "unavailable"
            }
        )
        raise HTTPException(
            status_code = 503,
            detail = "Redis unavailable"
        )

@app.post("/jobs", status_code=202)
def create_job(payload: JobRequest):
    job_id = str(uuid.uuid4())
    job_record = {
        "job_id": job_id,
        "task": payload.task,
        "duration": payload.duration,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    redis_key = f"job:{job_id}"

    queue_payload = json.dumps({
        "job_id": job_id,
        "task": payload.task,
        "duration": payload.duration,
    })

    try:
        with redis_client.pipeline(transaction=True) as pipe:
            pipe.hset(redis_key, mapping=job_record)
            pipe.expire(redis_key, 3600)
            pipe.lpush("jobs_queue", queue_payload)
            pipe.execute()

        logger.info(
            "Job created successfully",
            extra={
                "event": "job_created",
                "job_id": job_id,
                "task": payload.task,
                "duration": payload.duration
            }
        )
    except redis.RedisError:

        logger.exception(
            "Failed to create job",
            extra={
                "event": "job_creation_failed",
                "job_id": job_id,
                "task": payload.task
            }
        )
        raise HTTPException(
            status_code = 503,
            detail="Unable to create job: Redis unavailable"
        )

    return {
        "job_id" : job_id,
        "status" : "queued"
    }
      
@app.get("/jobs/{job_id}")
def read_job(job_id: uuid.UUID):
    redis_key = f"job:{str(job_id)}"
    
    try:
        job = redis_client.hgetall(redis_key)
    
    except redis.RedisError:

        logger.exception(
            "Failed to retrive job",
            extra={
                "event": "job_retrieval_failed",
                "job_id": str(job_id)
            }
        )
        raise HTTPException(
            status_code = 503,
            detail="redis unavailable"
        )
    if not job:

        logger.warning(
            "Job not found",
            extra={
                "event": "job_not_found",
                "job_id": str(job_id)
            }
        )
        raise HTTPException(
            status_code=404, 
            detail="Job not found"
            )
    
    logger.info(
        "Job retrieved successfully",
        extra={
            "event": "job_retrieved",
            "job_id": str(job_id)
        }
    )
    return job


