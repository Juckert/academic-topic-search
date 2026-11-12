import { describe, expect, it } from "vitest";
import { migrateLibrary } from "./storage";
import type { Topic } from "./models";

const topic: Topic = {
  id: "topic-a", title: "Тема из прежнего каталога", annotation: "Описание", annotation_origin: "generated",
  metadata: { year: 2026, department: null, program: null, work_type: null, source_url: null },
};
function legacy() {
  const query = { title: "Тема", annotation: "а".repeat(6000), department: "", year: "2026" };
  return {
    settings: { department: "", keepHistory: false },
    drafts: [{ id: "draft-a", query, updatedAt: 1, checkedAt: 1, links: ["topic-a"] }],
    history: [{ id: "check-a", query, at: 1, scopeCount: 500, view: { minimum: 50, limit: 10 },
      hits: [["topic-a", 86, false]] }],
  };
}

describe("browser storage compatibility", () => {
  it("preserves legacy text, links and the original demo score scale", () => {
    const input = legacy();
    const result = migrateLibrary(input, new Map([[topic.id, topic]]));
    expect(result.drafts[0].query.annotation).toHaveLength(6000);
    expect(result.drafts[0].links[0]).toEqual(topic);
    expect(result.history[0].result.hits[0].score).toBe(0.86);
    expect(result.history[0].result.score_type).toBe("word_overlap");
    expect(result.history[0].view.minimumScore).toBe(0.5);
    expect(result.settings.keepHistory).toBe(false);
    expect(input.history[0].hits[0][1]).toBe(86);
    expect(migrateLibrary(result, new Map())).toEqual(result);
  });
  it("keeps references when an old catalog entry is unavailable", () => {
    const result = migrateLibrary(legacy(), new Map());
    expect(result.drafts[0].links[0].id).toBe("topic-a");
    expect(result.drafts[0].links[0].metadata.source_url).toBeNull();
  });
  it("rejects unknown storage formats instead of replacing them", () => {
    expect(() => migrateLibrary({ schema_version: 100 }, new Map())).toThrow();
  });
});
