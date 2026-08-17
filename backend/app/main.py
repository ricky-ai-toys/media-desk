"""Media Desk — FastAPI entry point. Serves the API + static web shell."""
import datetime
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import config
from . import db
from .api.admin import admin as admin_router
from .api.routes import router as public_router
from .api.sse import event_stream
from .export import media_export
from .export.email import render_email

WEB = Path(__file__).resolve().parents[2] / "web" / "static"

_EDITION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_to_\d{4}-\d{2}-\d{2}$")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Media Desk", version="1.0.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.WEB.get("cors_origins") or ["http://localhost:8517", "http://127.0.0.1:8517"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(public_router, prefix="/api")
app.include_router(admin_router, prefix="/api")

app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/export/{edition_id}/{kind}")
def export(edition_id: str, kind: str):
    if not _EDITION_RE.fullmatch(edition_id):
        raise HTTPException(404, "edition not found")
    ed = db.edition_full(edition_id)
    if not ed:
        raise HTTPException(404, "edition not found")
    if kind == "csv":
        return PlainTextResponse(media_export.agenda_csv(ed), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="agenda_{edition_id}.csv"'})
    if kind == "email":
        return HTMLResponse(render_email(ed))
    if kind == "pdf":
        pdf = config.ROOT / "data" / f"media_weekly_{edition_id}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        if not _pdf_fresh(pdf, ed.get("created_at") or ""):
            ok = media_export.pdf_from_html(media_export.print_html(ed), pdf)
            if not ok:
                raise HTTPException(500, "pdf render failed")
        return FileResponse(pdf, media_type="application/pdf",
                            filename=f"International_Financial_Media_Weekly_{edition_id}.pdf")
    raise HTTPException(404, "unknown export kind")


def _pdf_fresh(pdf: Path, created_at: str) -> bool:
    """Reuse a rendered PDF unless the edition was updated after it."""
    if not pdf.exists() or not created_at:
        return False
    try:
        mtime = datetime.datetime.fromtimestamp(
            pdf.stat().st_mtime, tz=datetime.timezone.utc).isoformat()
    except OSError:
        return False
    return mtime >= created_at
