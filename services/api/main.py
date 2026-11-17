from fastapi import FastAPI
from fastapi import HTTPException
import uuid
from pydantic  import BaseModel

class job(BaseModel):
    compute: float
    cpu_spike: float | None = None
    duration: int
    error: str | None = None

app = FastAPI(title="HomeLab Reliability Platform API")

@app.post("/jobs", status_code=202)
def create_job(job: job):
    job_id = uuid.uuid4()
    jobs[job_id] = job.dict()
    return {"job_id": job_id}

@app.get("/health")
def read_health():
    return {"status": "ok"}

jobs: dict[uuid.UUID, dict] = {}
@app.get("/jobs/{job_id}")
def read_job(job_id: uuid.UUID):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id}


