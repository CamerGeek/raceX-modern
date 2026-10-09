import sys
from pathlib import Path

# Keep the copied legacy modules isolated while their imports are extracted.
legacy_path = Path(__file__).parent / "legacy"
if str(legacy_path) not in sys.path:
    sys.path.insert(0, str(legacy_path))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.meetings import router as meetings_router
from app.api.auth import router as auth_router
from app.api.races import router as races_router
from app.api.supabase_races import router as supabase_races_router
from app.api.turfomania import router as turfomania_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


app.include_router(meetings_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(races_router, prefix=settings.api_prefix)
app.include_router(supabase_races_router, prefix=settings.api_prefix)
app.include_router(turfomania_router, prefix=settings.api_prefix)
