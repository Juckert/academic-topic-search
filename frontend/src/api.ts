import { z } from "zod";
import { backendScoreSchema, filterOptionsSchema, querySchema, resultSchema } from "./models";
import type { FilterOptions, Query, SearchResult } from "./models";

export class ApiError extends Error {
  constructor(message: string, readonly code: string) {
    super(message);
    this.name = "ApiError";
  }
}

const mode = import.meta.env.VITE_SEARCH_MODE || "demo";
if (mode !== "demo" && mode !== "api") throw new Error("VITE_SEARCH_MODE должен быть demo или api.");
export const searchMode = mode;
const base = import.meta.env.VITE_API_BASE_URL || "/api/v1";
const baseUrl = new URL(base.endsWith("/") ? base : base + "/", globalThis.location?.origin ?? "http://localhost");
if (!["http:", "https:"].includes(baseUrl.protocol) || baseUrl.username || baseUrl.password ||
    baseUrl.search || baseUrl.hash) throw new Error("Некорректный адрес API.");

const apiResultSchema = resultSchema.extend({
  query: querySchema,
  method: z.enum(["bm25", "dense", "hybrid"]),
  score_type: backendScoreSchema,
  candidate_limit: z.number().int().min(1).max(50),
  candidate_count: z.number().int().nonnegative().max(50),
  hits: resultSchema.shape.hits.max(50),
});
const apiFiltersSchema = filterOptionsSchema.extend({ score_type: backendScoreSchema });

export function validateResult(value: unknown, query: Query): SearchResult {
  const result = apiResultSchema.parse(value);
  const retrievalType = { bm25: "bm25", dense: "cosine", hybrid: "rrf" }[result.method];
  const expectedType = result.reranker_enabled ? "reranker_logit" : retrievalType;
  const ids = new Set(result.hits.map((hit) => hit.id));
  if (result.score_type !== expectedType || ids.size !== result.hits.length ||
      result.hits.length !== result.candidate_count ||
      result.candidate_count > result.candidate_limit ||
      result.candidate_count > result.eligible_documents ||
      result.eligible_documents > result.corpus_size ||
      (result.status === "results") !== Boolean(result.hits.length) ||
      (result.empty_reason === null) !== Boolean(result.hits.length)) {
    throw new ApiError("Структура поискового ответа противоречит контракту.", "invalid_response");
  }
  for (const [index, hit] of result.hits.entries()) {
    if (hit.score_type !== result.score_type || hit.retrieval_score_type !== retrievalType ||
        (index > 0 && hit.score > result.hits[index - 1].score) ||
        !validScore(hit.score, hit.score_type) || !validScore(hit.retrieval_score, hit.retrieval_score_type) ||
        (hit.annotation === null) !== (hit.annotation_origin === "missing")) {
      throw new ApiError("Оценки или порядок результатов противоречат контракту.", "invalid_response");
    }
  }
  if (result.query.title !== query.title || result.query.annotation !== query.annotation ||
      result.query.filters.department !== query.filters.department ||
      result.query.filters.year !== query.filters.year) {
    throw new ApiError("Ответ относится к другому запросу.", "invalid_response");
  }
  return result;
}

function validScore(score: number, type: string): boolean {
  if (type === "bm25" || type === "rrf") return score >= 0;
  if (type === "cosine") return score >= -1.000001 && score <= 1.000001;
  return Number.isFinite(score);
}

async function readJson(response: Response): Promise<unknown> {
  if (!response.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    throw new ApiError("Сервер вернул ответ в неожиданном формате.", "invalid_response");
  }
  if (!response.body) throw new ApiError("Сервер вернул пустой ответ.", "invalid_response");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let bytes = 0;
  try {
    while (true) {
      const part = await reader.read();
      if (part.done) break;
      bytes += part.value.byteLength;
      if (bytes > 3 * 1024 * 1024) {
        await reader.cancel();
        throw new ApiError("Ответ превышает допустимый размер.", "invalid_response");
      }
      chunks.push(part.value);
    }
  } finally {
    reader.releaseLock();
  }
  const combined = new Uint8Array(bytes);
  let position = 0;
  for (const chunk of chunks) { combined.set(chunk, position); position += chunk.byteLength; }
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(combined));
}

async function request(path: string, body?: Query, signal?: AbortSignal): Promise<unknown> {
  const controller = new AbortController();
  const cancel = () => controller.abort(signal?.reason);
  if (signal?.aborted) cancel();
  signal?.addEventListener("abort", cancel, { once: true });
  const timeout = setTimeout(() => controller.abort(new DOMException("Timeout", "TimeoutError")), 30000);
  try {
    const response = await fetch(new URL(path, baseUrl), {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      credentials: "omit",
      redirect: "error",
      cache: "no-store",
    });
    if (!response.ok) {
      const message = response.status === 422 ? "Проверьте длину текста и значения фильтров."
        : response.status === 503 ? "Поиск временно недоступен. Повторите попытку позже."
        : "Сервер не выполнил запрос. Повторите попытку.";
      throw new ApiError(message, "http_" + response.status);
    }
    return await readJson(response);
  } catch (error) {
    if (controller.signal.aborted) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      throw new ApiError("Время ожидания поиска истекло. Повторите попытку.", "timeout");
    }
    if (error instanceof ApiError) throw error;
    if (error instanceof SyntaxError || error instanceof TypeError && !(error.message.includes("fetch"))) {
      throw new ApiError("Не удалось прочитать ответ сервера.", "invalid_response");
    }
    throw new ApiError("Не удалось связаться с сервером поиска.", "network");
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", cancel);
  }
}

export async function loadFilters(signal?: AbortSignal): Promise<FilterOptions> {
  if (searchMode === "demo") return (await import("./demo")).demoFilters;
  try {
    const options = apiFiltersSchema.parse(await request("filters", undefined, signal));
    if (new Set(options.departments).size !== options.departments.length ||
        new Set(options.years).size !== options.years.length) {
      throw new ApiError("Справочники содержат повторяющиеся значения.", "invalid_response");
    }
    return options;
  } catch (error) {
    if (error instanceof z.ZodError) throw new ApiError("Справочники не соответствуют контракту API.", "invalid_response");
    throw error;
  }
}

export async function searchTopics(input: Query, signal: AbortSignal): Promise<SearchResult> {
  const query = querySchema.parse(input);
  if (searchMode === "demo") {
    const { demoSearch } = await import("./demo");
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    return demoSearch(query);
  }
  try {
    return validateResult(await request("search", query, signal), query);
  } catch (error) {
    if (error instanceof z.ZodError) throw new ApiError("Поисковый ответ не соответствует контракту API.", "invalid_response");
    throw error;
  }
}
