import type { Query, ScoreType } from "./models";

const number = new Intl.NumberFormat("ru", { maximumFractionDigits: 3 });
const rankNumber = new Intl.NumberFormat("ru", { maximumFractionDigits: 6 });
const date = new Intl.DateTimeFormat("ru", { dateStyle: "short", timeStyle: "short" });
export const formatDate = (value: number) => date.format(value);
export const scoreLabel: Record<ScoreType, string> = {
  bm25: "BM25", cosine: "Косинусное сходство", rrf: "RRF",
  reranker_logit: "Оценка reranker", word_overlap: "по словам",
};
export const formatScore = (value: number, type: ScoreType) =>
  type === "word_overlap" ? Math.round(value * 100) + "%" : type === "rrf" ? rankNumber.format(value) : number.format(value);
export const scopeText = (query: Query) =>
  [query.filters.department, query.filters.year].filter(Boolean).join(" · ") || "Весь каталог";
export const isAbort = (error: unknown) => error instanceof DOMException && error.name === "AbortError";
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Не удалось выполнить действие.";
