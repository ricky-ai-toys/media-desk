"""SSE event stream: pushes pipeline_state changes (daily ingest pulses)."""
import asyncio
import json

from fastapi.responses import StreamingResponse

from .. import db

_last = {"stage": None, "status": None, "updated_at": None}


def _changed() -> dict | None:
    p = db.get_pipeline()
    if not p:
        return None
    if (p["stage"], p["status"], p["updated_at"]) != (
            _last["stage"], _last["status"], _last["updated_at"]):
        _last.update(stage=p["stage"], status=p["status"], updated_at=p["updated_at"])
        return p
    return None


async def event_stream():
    async def gen():
        yield "event: hello\ndata: {}\n\n".format(
            json.dumps({"stage": "connected", "state": db.get_pipeline()}, ensure_ascii=False))
        while True:
            ev = await asyncio.to_thread(_changed)
            if ev:
                yield f"event: pipeline\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})