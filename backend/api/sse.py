"""Server-sent-event frame formatting shared by the streaming endpoints."""

import json


def sse(event: str, data: object) -> str:
    """One server-sent event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
