from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from app.models.schemas import (
    LabelValidationRequest, 
    LabelValidationResult, 
    AnalysisRequest
)
from app.services.analysis_engine import validate_is_label, run_analysis_job
from app.stores.job_store import job_store
import asyncio
import json

router = APIRouter()

@router.post("/validate", response_model=LabelValidationResult)
async def validate_image(request: LabelValidationRequest):
    """
    Validates if the uploaded image is a food label and detects its category.
    """
    try:
        result = await validate_is_label(request.base64Image)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/jobs")
async def create_analysis_job(request: AnalysisRequest):
    """
    Submits an analysis job and returns the jobId.
    """
    try:
        job_id = await job_store.create_job(
            request.base64Image, 
            request.options.model_dump(mode='json'),
            request.panelCount,
            request.panelOffsets
        )
        # Start background task to run the analysis, fire and forget
        asyncio.create_task(run_analysis_job(job_id))
        return {"jobId": job_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Poll job status and get final result.
    """
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    response = {
        "status": job.status,
        "panelCount": job.panel_count,
        "panelOffsets": job.panel_offsets
    }
    if job.result:
        response["result"] = job.result
    if job.error:
        response["error"] = job.error
        
    return response

@router.get("/jobs/{job_id}/image")
async def get_job_image(job_id: str):
    """
    Get the base64 image payload that was submitted for this job.
    """
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {"image": job.image_base64}

@router.get("/jobs/{job_id}/stream")
async def stream_job_events(job_id: str, request: Request):
    """
    Streams Server-Sent Events for a job.
    If the job is ongoing, it replays past events, then continues streaming new ones.
    If the job is complete, it replays everything and closes.
    """
    sub_result = await job_store.subscribe(job_id)
    if not sub_result:
        raise HTTPException(status_code=404, detail="Job not found")
        
    past_events, queue = sub_result
    job = await job_store.get_job(job_id)
    
    async def event_stream():
        try:
            # Yield past events first
            for event in past_events:
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            
            # If the job is already complete or errored, we yield past events and stop.
            if job.status in ["complete", "error"]:
                return
                
            # If still running, wait for new events
            while True:
                if await request.is_disconnected():
                    break
                event = await queue.get()
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
                
                # Check for termination events
                if event['event'] in ['result', 'error'] or event['event'] == 'done':
                    break
                    
        finally:
            await job_store.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream"
    )
