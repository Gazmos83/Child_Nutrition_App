import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, fetchJson, readDetail, setUnauthorizedHandler } from "../api";

function response(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("fetchJson", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setUnauthorizedHandler(null);
  });

  it("sends JSON and returns the parsed body", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(201, { id: "u1" }));
    const body = await fetchJson<{ id: string }>("/api/auth/register", {
      method: "POST",
      body: { email: "a@example.com", password: "correct horse battery" },
    });
    expect(body).toEqual({ id: "u1" });
    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(init?.headers).toEqual({ "content-type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual({
      email: "a@example.com",
      password: "correct horse battery",
    });
  });

  it("a 204 resolves to undefined", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    await expect(fetchJson<void>("/api/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("a 401 notifies the handler and throws", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response(401, { detail: "Sign in to continue" }),
    );
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    await expect(fetchJson("/api/auth/me")).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("other errors carry the server detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      response(409, { detail: "An account with this email already exists" }),
    );
    const error = await fetchJson("/api/auth/register", { method: "POST", body: {} }).catch(
      (e: unknown) => e,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).detail).toBe("An account with this email already exists");
  });
});

describe("readDetail", () => {
  it("joins validation messages and falls back to the status text", async () => {
    const validation = response(422, { detail: [{ msg: "age too high" }, { msg: "no sex" }] });
    expect(await readDetail(validation)).toBe("age too high no sex");
    expect(await readDetail(new Response("nope", { status: 502, statusText: "Bad Gateway" }))).toBe(
      "Bad Gateway",
    );
  });
});
