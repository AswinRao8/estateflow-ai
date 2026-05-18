from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Dashboard"])

_HTML = (Path(__file__).parent.parent / "static" / "dashboard.html").read_text(encoding="utf-8")


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard() -> str:
    return _HTML
