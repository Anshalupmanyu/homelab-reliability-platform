from fastapi import FastAPI, HTTPException
from typing import Literal
import uuid
from pydantic  import BaseModel, Field
from datetime import datetime, timezone
from redis_client import redis_client
import redis
import json


app = FastAPI(title="HomeLab Reliability Platform API")
FastAPIRedis(app)

class JobRequest(BaseModel):
    task: Literal["compute", "error", "cpu_spike", "memory_leak"] = "compute"
    duration: int = Field(default=2, ge=1, le=60)

@app.get("/health")
def read_health():
    try:
        redis_client.ping()
        return {
            "status" : "ok",
            "redis" : "connected"
        }
    except redis.RedisError:
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
    
    except redis.RedisError:
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
    redis_key = f"job:{job_id}"
    
    try:
        job = redis_client.hgetall(redis_key)
    
    except redis.RedisError:
        raise HTTPException(
            status_code = 503,
            detail="redis unavailable"
        )
    if not job:
        raise HTTPException(
            status_code=404, 
            detail="Job not found"
            )
    return job


