import { describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./api";

describe("apiFetch", () => {
  it("turns an error response into ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 401 })));
    await expect(apiFetch("/history")).rejects.toBeInstanceOf(ApiError);
  });
});
