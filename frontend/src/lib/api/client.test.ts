/** Project-creation and error-handling tests for the API boundary (requirement 29). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, getToken, setToken } from "./client";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    blob: async () => new Blob([JSON.stringify(body)]),
    headers: new Headers(),
  } as unknown as Response;
}

describe("api client", () => {
  beforeEach(() => {
    setToken(null);
    vi.restoreAllMocks();
  });

  afterEach(() => {
    setToken(null);
  });

  it("stores and clears the token", () => {
    expect(getToken()).toBeNull();
    setToken("abc");
    expect(getToken()).toBe("abc");
    setToken(null);
    expect(getToken()).toBeNull();
  });

  it("creates a project with the payload the backend expects", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ id: "p1", name: "Summer drop", scenes: [], media: [] }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);
    setToken("token-123");

    const project = await api.createProject({
      name: "Summer drop",
      description: "New collection",
      style: "luxury",
      platform: "instagram_reels",
    });

    expect(project.id).toBe("p1");

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/v1\/projects$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toMatchObject({
      name: "Summer drop",
      style: "luxury",
      platform: "instagram_reels",
    });
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer token-123");
    expect((init.headers as Headers).get("Content-Type")).toBe("application/json");
  });

  it("turns a backend error body into an ApiError carrying its message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "validation_error",
              message: "Please upload at least one image.",
              details: [{ field: "scenes", problem: "too short" }],
            },
          },
          422,
        ),
      ),
    );

    await expect(api.generatePlan("p1", {})).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      code: "validation_error",
      message: "Please upload at least one image.",
    });
  });

  it("clears the token on a 401 so the app can send the user back to sign-in", async () => {
    setToken("expired");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { code: "authentication_error", message: "Please sign in." } }, 401),
      ),
    );

    await expect(api.listProjects()).rejects.toBeInstanceOf(ApiError);
    expect(getToken()).toBeNull();
  });

  it("reports an unreachable server in plain language", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed to fetch")));

    await expect(api.capabilities()).rejects.toMatchObject({
      status: 0,
      code: "network_error",
      message: expect.stringContaining("Could not reach the server"),
    });
  });

  it("returns undefined for a 204 rather than trying to parse a body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(null, 204)));
    await expect(api.deleteProject("p1")).resolves.toBeUndefined();
  });

  it("builds the search query for the project list", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 24, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.listProjects({ limit: 10, offset: 20, search: "school supplies" });
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "limit=10&offset=20&search=school+supplies",
    );
  });

  it("marks a 503 as an unavailable capability", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "provider_unavailable",
              message: "Voice-over is unavailable because no text-to-speech provider is configured.",
            },
          },
          503,
        ),
      ),
    );

    try {
      await api.generateVoiceOver("p1");
      expect.unreachable("should have thrown");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).isUnavailable).toBe(true);
    }
  });
});

describe("media URL resolution", () => {
  it("makes relative storage links absolute against the API host", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          id: "p1",
          thumbnail_url: "/api/v1/files/users/1/a-thumb.jpg",
          download_url: null,
          scenes: [
            { id: "s1", media: { id: "m1", url: "/api/v1/files/users/1/a.jpg", thumbnail_url: null } },
          ],
          audio: { media: { url: "/api/v1/files/users/1/track.mp3" } },
        }),
      ),
    );

    const project = (await api.getProject("p1")) as unknown as {
      thumbnail_url: string;
      scenes: Array<{ media: { url: string } }>;
      audio: { media: { url: string } };
    };

    expect(project.thumbnail_url).toMatch(/^https?:\/\/.+\/api\/v1\/files\/users\/1\/a-thumb\.jpg$/);
    expect(project.scenes[0].media.url).toMatch(/^https?:\/\/.+\/a\.jpg$/);
    expect(project.audio.media.url).toMatch(/^https?:\/\/.+\/track\.mp3$/);
  });

  it("leaves absolute URLs alone, so S3 and CDN links are untouched", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ id: "p1", thumbnail_url: "https://cdn.example.com/a.jpg", scenes: [] }),
      ),
    );
    const project = (await api.getProject("p1")) as unknown as { thumbnail_url: string };
    expect(project.thumbnail_url).toBe("https://cdn.example.com/a.jpg");
  });
});
