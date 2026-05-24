from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Dashboard"])

_DASHBOARD_PATH = Path(__file__).parent.parent / "static" / "dashboard.html"

try:
    _HTML: str = _DASHBOARD_PATH.read_text(encoding="utf-8")
except FileNotFoundError:
    _HTML = "<h1>Dashboard unavailable — dashboard.html not found</h1>"


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> str:
    return _HTML
