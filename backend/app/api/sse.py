"""SSE event stream: pushes pipeline_state changes (daily ingest pulses)."""
import asyncio
import json

from fastapi.responses import StreamingResponse

from .. import db


def _changed(last: tuple) -> tuple[dict | None, tuple]:
    """Return (pipeline dict, new last-seen) when state moved since `last`."""
    p = db.get_pipeline()
    if not p:
        return None, last
    cur = (p["stage"], p["status"], p["updated_at"])
    if cur != last:
        return p, cur
    return None, last


async def event_stream():
    async def gen():
        last: tuple = (None, None, None)
        yield "event: hello\ndata: {}\n\n".format(
            json.dumps({"stage": "connected", "state": db.get_pipeline()}, ensure_ascii=False))
        while True:
            ev, last = await asyncio.to_thread(_changed, last)
            if ev:
                yield f"event: pipeline\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})