import { z } from "zod";

export const limits = { title: 500, annotation: 3498, candidates: 50 } as const;
export const backendScoreSchema = z.enum(["bm25", "cosine", "rrf", "reranker_logit"]);
export const scoreSchema = z.enum(["bm25", "cosine", "rrf", "reranker_logit", "word_overlap"]);
export const filtersSchema = z.object({
  department: z.string().min(1).max(300).nullable(),
  year: z.number().int().min(1900).max(2200).nullable(),
});
export const querySchema = z.object({
  title: z.string().trim().min(1).max(limits.title).refine(
    (text) => /[\p{L}\p{N}]/u.test(text), "Введите название темы.",
  ),
  annotation: z.string().trim().max(limits.annotation).nullable().transform((value) => value || null),
  filters: filtersSchema,
});
export const storedQuerySchema = querySchema.extend({
  annotation: z.string().trim().max(6000).nullable(),
});

export function safeSourceUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password
      ? url.href : null;
  } catch {
    return null;
  }
}

export const topicSchema = z.object({
  id: z.string().min(1).max(128),
  title: z.string().min(1).max(500),
  annotation: z.string().max(12000).nullable(),
  annotation_origin: z.enum(["original", "generated", "unknown", "missing"]),
  metadata: z.object({
    year: z.number().int().min(1900).max(2200).nullable(),
    department: z.string().max(300).nullable(),
    program: z.string().max(300).nullable(),
    work_type: z.string().max(100).nullable(),
    source_url: z.string().max(2048).nullable().transform(safeSourceUrl),
  }),
});
export const hitSchema = topicSchema.extend({
  score: z.number().finite(),
  score_type: scoreSchema,
  retrieval_score: z.number().finite(),
  retrieval_score_type: scoreSchema,
});
export const resultSchema = z.object({
  api_version: z.literal("1.0"),
  search_id: z.string().min(1).max(128),
  query: storedQuerySchema,
  method: z.enum(["bm25", "dense", "hybrid", "word_overlap"]),
  reranker_enabled: z.boolean(),
  score_type: scoreSchema,
  dataset_id: z.string().min(1).max(128),
  dataset_version: z.string().min(1).max(128),
  pipeline_version: z.string().min(1).max(128),
  corpus_size: z.number().int().nonnegative(),
  eligible_documents: z.number().int().nonnegative(),
  candidate_limit: z.number().int().min(1).max(500),
  candidate_count: z.number().int().nonnegative().max(500),
  status: z.enum(["results", "empty"]),
  empty_reason: z.enum(["filters_or_exclusions", "no_candidates"]).nullable(),
  hits: z.array(hitSchema).max(500),
});
export const filterOptionsSchema = z.object({
  api_version: z.literal("1.0"),
  dataset_id: z.string().min(1).max(128),
  dataset_version: z.string().min(1).max(128),
  corpus_size: z.number().int().nonnegative(),
  departments: z.array(z.string().min(1).max(300)).max(2000),
  years: z.array(z.number().int().min(1900).max(2200)).max(301),
  score_type: scoreSchema,
  candidate_limit: z.number().int().min(1).max(limits.candidates),
});
export type Query = z.infer<typeof querySchema>;
export type Topic = z.infer<typeof topicSchema>;
export type Hit = z.infer<typeof hitSchema>;
export type SearchResult = z.infer<typeof resultSchema>;
export type FilterOptions = z.infer<typeof filterOptionsSchema>;
export type ScoreType = z.infer<typeof scoreSchema>;
export type Page = "search" | "history" | "works" | "profile";

export const viewSchema = z.object({
  minimumScore: z.number().finite().nullable(),
  limit: z.union([z.literal(5), z.literal(10), z.literal(20)]),
});
export const draftSchema = z.object({
  id: z.string().min(1),
  query: storedQuerySchema,
  updatedAt: z.number().finite().nonnegative(),
  checkedAt: z.number().finite().nonnegative().nullable(),
  links: z.array(topicSchema),
});
export const historySchema = z.object({
  id: z.string().min(1),
  at: z.number().finite().nonnegative(),
  query: storedQuerySchema,
  view: viewSchema,
  result: resultSchema,
});
export const settingsSchema = z.object({
  department: z.string().nullable(),
  keepHistory: z.boolean(),
});
export const librarySchema = z.object({
  schema_version: z.literal(2),
  settings: settingsSchema,
  drafts: z.array(draftSchema),
  history: z.array(historySchema),
});
export type View = z.infer<typeof viewSchema>;
export type Draft = z.infer<typeof draftSchema>;
export type HistoryEntry = z.infer<typeof historySchema>;
export type Settings = z.infer<typeof settingsSchema>;
export type Library = z.infer<typeof librarySchema>;

export const defaultView: View = { minimumScore: null, limit: 5 };
export const emptyQuery = (department: string | null = null): Query => ({
  title: "", annotation: null, filters: { department, year: null },
});
export const emptyLibrary = (): Library => ({
  schema_version: 2,
  settings: { department: null, keepHistory: true },
  drafts: [], history: [],
});
export const sameText = (a: Query, b: Query) =>
  a.title.trim() === b.title.trim() && (a.annotation ?? "").trim() === (b.annotation ?? "").trim();
export const newId = () => [...crypto.getRandomValues(new Uint32Array(4))]
  .map((value) => value.toString(16).padStart(8, "0")).join("");
