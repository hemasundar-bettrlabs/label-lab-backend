from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
from app.routes import route

load_dotenv()

app = FastAPI(
    title="Label Validator Backend",
    description="Backend for Label Validator V4",
    version="4.0.0"
)

# CORS Configuration
# For production, set CORS_ALLOWED_ORIGINS in .env (comma-separated if multiple)
cors_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
origins = [origin.strip() for origin in cors_origins_str.split(",")]

# Only allow credentials if we are not using a wildcard *
allow_creds = "*" not in origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(route.router, prefix="/api")

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "Label Validator Backend"}
