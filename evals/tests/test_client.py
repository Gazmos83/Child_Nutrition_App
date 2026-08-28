import json

import httpx

from harness.client import ServiceClient


def test_request_shapes_and_cookie_reuse() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/api/auth/register":
            return httpx.Response(
                201, json={"id": "u1", "email": "e"}, headers={"set-cookie": "session=tok; Path=/"}
            )
        if path == "/api/children":
            return httpx.Response(201, json={"id": "c1"})
        if path.endswith("/feedings"):
            return httpx.Response(201, json={})
        if path == "/api/chat":
            return httpx.Response(
                200, json={"answer": "a", "intent": "tool", "tools": [], "citations": []}
            )
        if path == "/api/ask":
            return httpx.Response(200, json={"answer": "a", "citations": [], "retrieval": {}})
        return httpx.Response(404)

    client = ServiceClient("http://test")
    client.http = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))

    client.register()
    child = client.save_child({"age_months": 8})
    client.log_feeds(
        child["id"], [{"fed_at": "t", "feeding_type": "formula", "quantity": 1, "unit": "ml"}]
    )
    client.chat("hi", child["id"], "basic")
    client.ask("q", "advanced")

    bodies = {r.url.path: json.loads(r.content) for r in seen if r.content}
    assert bodies["/api/chat"] == {
        "message": "hi",
        "strategy": "basic",
        "stream": False,
        "child_id": "c1",
    }
    assert bodies["/api/ask"] == {"question": "q", "strategy": "advanced", "stream": False}
    assert "child" not in bodies["/api/chat"] and "feeding_log" not in bodies["/api/chat"]
    # The session cookie set by register rides along on every later request.
    assert all("session=tok" in r.headers.get("cookie", "") for r in seen[1:])
