import { z } from "zod";
import source from "@catalog";
import { terms } from "./text";
import { topicSchema, newId } from "./models";
import type { FilterOptions, Query, SearchResult, Topic } from "./models";

const datasetSchema = z.object({
  dataset_id: z.string(),
  dataset_version: z.string(),
  topics: z.array(topicSchema).min(1),
});
const dataset = datasetSchema.parse(source);
export const demoTopics: Topic[] = dataset.topics;
export const demoTopicMap = new Map(demoTopics.map((topic) => [topic.id, topic]));
const collator = new Intl.Collator("ru");
function overlap(left: Set<string>, right: Set<string>): number {
  const count = [...right].filter((word) => left.has(word)).length;
  return left.size + right.size ? 2 * count / (left.size + right.size) : 0;
}
export const demoFilters: FilterOptions = {
  api_version: "1.0",
  dataset_id: dataset.dataset_id,
  dataset_version: dataset.dataset_version,
  corpus_size: demoTopics.length,
  departments: [...new Set(demoTopics.flatMap((topic) => topic.metadata.department ? [topic.metadata.department] : []))].sort(collator.compare),
  years: [...new Set(demoTopics.flatMap((topic) => topic.metadata.year ? [topic.metadata.year] : []))].sort((a, b) => b - a),
  score_type: "word_overlap",
  candidate_limit: 50,
};

export function demoSearch(query: Query): SearchResult {
  const title = terms(query.title);
  const extended = new Set([...title, ...terms(query.annotation ?? "")]);
  const eligible = demoTopics.filter(({ metadata }) =>
    (!query.filters.department || metadata.department === query.filters.department) &&
    (!query.filters.year || metadata.year === query.filters.year),
  );
  const hits = eligible.map((topic) => {
    const score = Math.max(overlap(title, terms(topic.title)), overlap(extended, terms(topic.title)));
    return { ...topic, score, score_type: "word_overlap" as const, retrieval_score: score, retrieval_score_type: "word_overlap" as const };
  }).filter((hit) => hit.score > 0).sort((a, b) => b.score - a.score || collator.compare(a.id, b.id)).slice(0, 50);
  return {
    api_version: "1.0", search_id: newId(), query,
    dataset_id: dataset.dataset_id, dataset_version: dataset.dataset_version,
    pipeline_version: "word-overlap-v1", method: "word_overlap", reranker_enabled: false,
    score_type: "word_overlap", corpus_size: demoTopics.length, eligible_documents: eligible.length,
    candidate_limit: 50, candidate_count: hits.length,
    status: hits.length ? "results" : "empty",
    empty_reason: hits.length ? null : eligible.length ? "no_candidates" : "filters_or_exclusions",
    hits,
  };
}
