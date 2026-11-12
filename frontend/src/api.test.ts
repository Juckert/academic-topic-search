import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { formatScore } from "./format";
import type { Query } from "./models";

const spec = JSON.parse(readFileSync(new URL("../../docs/openapi.json", import.meta.url), "utf8"));
const examples = spec.paths["/search"].post.responses["200"].content["application/json"].examples;
const sample = () => structuredClone(examples.results.value);
const query: Query = sample().query;
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
let api: typeof import("./api");

beforeEach(async () => {
  vi.resetModules();
  vi.stubEnv("VITE_SEARCH_MODE", "api");
  vi.stubEnv("VITE_API_BASE_URL", "/api/v1");
  vi.stubGlobal("location", { origin: "http://localhost" });
  api = await import("./api");
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("API contract", () => {
  it("accepts the documented success and empty responses", () => {
    expect(api.validateResult(sample(), query).hits).toHaveLength(1);
    expect(api.validateResult(examples.empty.value, query).status).toBe("empty");
  });
  it("preserves raw scores and hides unsafe source URLs", () => {
    const value = sample();
    value.hits[0].metadata.source_url = "javascript:alert(1)";
    const result = api.validateResult(value, query);
    expect(result.hits[0].metadata.source_url).toBeNull();
    expect(formatScore(result.hits[0].score, result.score_type)).not.toContain("%");
    expect(formatScore(0.86, "word_overlap")).toBe("86%");
  });
  it.each(["duplicate", "count", "scale", "nonfinite", "negative", "query", "order"])("rejects inconsistent %s responses", (caseName) => {
    const value = sample();
    if (caseName === "duplicate") { value.hits.push(value.hits[0]); value.candidate_count = 2; }
    if (caseName === "count") value.candidate_count = 2;
    if (caseName === "scale") value.hits[0].score_type = "cosine";
    if (caseName === "nonfinite") value.hits[0].score = Infinity;
    if (caseName === "negative") value.hits[0].score = -1;
    if (caseName === "query") value.query.title = "Другая тема";
    if (caseName === "order") {
      value.hits.push({ ...value.hits[0], id: "other-topic", score: 99 });
      value.candidate_count = 2;
    }
    expect(() => api.validateResult(value, query)).toThrow();
  });
  it("sends numeric years and only the documented request fields", async () => {
    const fetch = vi.fn().mockResolvedValue(json(sample()));
    vi.stubGlobal("fetch", fetch);
    await api.searchTopics(query, new AbortController().signal);
    const [url, init] = fetch.mock.calls[0];
    expect(String(url)).toBe("http://localhost/api/v1/search");
    expect(JSON.parse(init.body)).toEqual(query);
    expect(JSON.parse(init.body).filters.year).toBe(2026);
    expect(init.credentials).toBe("omit");
    expect(init.redirect).toBe("error");
  });
  it("does not substitute demo output for HTTP errors", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 }));
    vi.stubGlobal("fetch", fetch);
    await expect(api.searchTopics(query, new AbortController().signal)).rejects.toMatchObject({ code: "http_503" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("normalizes empty annotations before sending", async () => {
    const fetch = vi.fn().mockResolvedValue(json(sample()));
    vi.stubGlobal("fetch", fetch);
    await api.searchTopics({ ...query, annotation: "   " }, new AbortController().signal);
    expect(JSON.parse(fetch.mock.calls[0][1].body).annotation).toBeNull();
  });
  it("rejects HTML responses and oversized bodies", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html></html>", { headers: { "Content-Type": "text/html" } })));
    await expect(api.searchTopics(query, new AbortController().signal)).rejects.toMatchObject({ code: "invalid_response" });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(" ".repeat(3 * 1024 * 1024 + 1),
      { headers: { "Content-Type": "application/json" } })));
    await expect(api.searchTopics(query, new AbortController().signal)).rejects.toMatchObject({ code: "invalid_response" });
  });
  it("cancels obsolete requests", async () => {
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) =>
      init.signal.addEventListener("abort", () => reject(init.signal.reason)))));
    const controller = new AbortController();
    const pending = api.searchTopics(query, controller.signal);
    const assertion = expect(pending).rejects.toMatchObject({ name: "AbortError" });
    controller.abort();
    await assertion;
  });
  it("bounds request time", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) =>
      init.signal.addEventListener("abort", () => reject(init.signal.reason)))));
    const pending = api.searchTopics(query, new AbortController().signal);
    const assertion = expect(pending).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(30001);
    await assertion;
  });
});
