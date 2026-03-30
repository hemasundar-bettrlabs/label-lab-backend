import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import uuid

class Job:
    def __init__(self, job_id: str, image_base64: str, options: dict, panel_count: int = 1, panel_offsets: Optional[list] = None):
        self.id = job_id
        self.status = "pending" # pending, running, complete, error
        self.events = []
        self.result = None
        self.error = None
        self.created_at = datetime.utcnow()
        self.image_base64 = image_base64
        self.options = options
        self.panel_count = panel_count
        self.panel_offsets = panel_offsets
        self.listeners = []

class JobStore:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task = None

    def _ensure_cleanup_task(self):
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self.cleanup_loop())

    async def create_job(self, image_base64: str, options: dict, panel_count: int = 1, panel_offsets: Optional[list] = None) -> str:
        self._ensure_cleanup_task()
        job_id = str(uuid.uuid4())
        async with self._lock:
            self.jobs[job_id] = Job(job_id, image_base64, options, panel_count, panel_offsets)
        return job_id

    async def get_job(self, job_id: str) -> Optional[Job]:
        async with self._lock:
            return self.jobs.get(job_id)

    async def update_status(self, job_id: str, status: str):
        async with self._lock:
            if job_id in self.jobs:
                self.jobs[job_id].status = status

    async def add_event(self, job_id: str, event_type: str, data: dict):
        async with self._lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                event = {"event": event_type, "data": data}
                job.events.append(event)
                # Notify listeners
                for q in job.listeners:
                    await q.put(event)

    async def set_result(self, job_id: str, result: dict):
        async with self._lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.result = result
                job.status = "complete"

    async def set_error(self, job_id: str, error: str):
        async with self._lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.error = error
                job.status = "error"

    async def subscribe(self, job_id: str) -> Optional[Tuple[List[dict], asyncio.Queue]]:
        async with self._lock:
            if job_id not in self.jobs:
                return None
            job = self.jobs[job_id]
            q = asyncio.Queue()
            job.listeners.append(q)
            return list(job.events), q

    async def unsubscribe(self, job_id: str, q: asyncio.Queue):
        async with self._lock:
            if job_id in self.jobs:
                try:
                    self.jobs[job_id].listeners.remove(q)
                except ValueError:
                    pass

    async def cleanup_loop(self):
        while True:
            await asyncio.sleep(600) # every 10 mins
            now = datetime.utcnow()
            async with self._lock:
                expired = [jid for jid, j in self.jobs.items() if (now - j.created_at) > timedelta(minutes=30)]
                for jid in expired:
                    del self.jobs[jid]

job_store = JobStore()
