"""
Development entry point.

Run with:
    uvicorn main:app --reload

Or use the app module directly:
    uvicorn app.main:app --reload
"""
from app.main import app  # noqa: F401 — re-exported for uvicorn

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)