"""Media Desk — FastAPI entry point. Serves the API + static web shell."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from . import db
from .api.admin import admin as admin_router
from .api.routes import router as public_router
from .api.sse import event_stream
from .export import media_export

app = FastAPI(title="Media Desk", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

WEB = Path(__file__).resolve().parents[2] / "web" / "static"


@app.on_event("startup")
def _startup():
    db.init_db()


app.include_router(public_router, prefix="/api")
app.include_router(admin_router, prefix="/api")

app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/export/{edition_id}/{kind}")
def export(edition_id: str, kind: str):
    ed = db.edition_full(edition_id)
    if not ed:
        return {"error": "edition not found"}
    if kind == "csv":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(media_export.agenda_csv(ed), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="agenda_{edition_id}.csv"'})
    if kind == "email":
        from fastapi.responses import HTMLResponse
        from .export.email import render_email
        return HTMLResponse(render_email(ed))
    if kind == "pdf":
        pdf = config.ROOT / "data" / f"media_weekly_{edition_id}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        ok = media_export.pdf_from_html(media_export.print_html(ed), pdf)
        if not ok:
            raise RuntimeError("pdf render failed")
        return FileResponse(pdf, media_type="application/pdf",
                            filename=f"International_Financial_Media_Weekly_{edition_id}.pdf")
    return {"error": "unknown kind"}