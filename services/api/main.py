from fastapi import FastAPI, HTTPException
from typing import Literal
import uuid
from pydantic  import BaseModel, Field
from datetime import datetime, timezone

app = FastAPI(title="HomeLab Reliability Platform API")

jobs: dict[str, dict] = {}

class jobRequest(BaseModel):
    task: Literal["compute", "error", "cpu_spike", "memory_leak"] = "compute"
    duration: int = Field(default=2, ge=1, le=60)

@app.get("/health")
def read_health():
    return {"status": "ok"}

@app.post("/jobs", status_code=202)
def create_job(payload: jobRequest):
    job_id = str(uuid.uuid4())
    job_record = {
        "job_id": job_id,
        "task": payload.task,
        "duration": payload.duration,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    jobs[job_id] = job_record
    return {"job_id": job_id, "status": "queued"} 

jobs: dict[uuid.UUID, dict] = {}
@app.get("/jobs/{job_id}")
def read_job(job_id: uuid.UUID):
    key = str(job_id)
    if key not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[key]


