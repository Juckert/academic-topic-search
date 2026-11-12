import { z } from "zod";
import { emptyLibrary, librarySchema } from "./models";
import type { Library, Query, SearchResult, Topic } from "./models";

const legacyQuery = z.object({
  title: z.string(), annotation: z.string(), department: z.string(), year: z.string(),
});
const legacySchema = z.object({
  settings: z.object({ department: z.string(), keepHistory: z.boolean() }),
  drafts: z.array(z.object({
    id: z.string(), query: legacyQuery, updatedAt: z.number(),
    checkedAt: z.number().nullable(), links: z.array(z.string()),
  })),
  history: z.array(z.object({
    id: z.string(), at: z.number(), query: legacyQuery,
    view: z.object({ minimum: z.number(), limit: z.union([z.literal(5), z.literal(10), z.literal(20)]) }),
    scopeCount: z.number(),
    hits: z.array(z.tuple([z.string(), z.number(), z.boolean()])),
  })),
});
const convertQuery = (value: z.infer<typeof legacyQuery>): Query => ({
  title: value.title, annotation: value.annotation || null,
  filters: { department: value.department || null, year: value.year ? Number(value.year) : null },
});

export function migrateLibrary(value: unknown, catalog: Map<string, Topic>): Library {
  if (value === undefined) return emptyLibrary();
  const modern = librarySchema.safeParse(value);
  if (modern.success) return modern.data;
  const old = legacySchema.parse(value);
  const getTopic = (id: string): Topic => catalog.get(id) ?? {
    id, title: "Запись каталога " + id, annotation: null, annotation_origin: "missing",
    metadata: { year: null, department: null, program: null, work_type: null, source_url: null },
  };
  const history = old.history.map((entry) => {
    const query = convertQuery(entry.query);
    const hits = entry.hits.map(([id, percent]) => ({
      ...getTopic(id), score: percent / 100, score_type: "word_overlap" as const,
      retrieval_score: percent / 100, retrieval_score_type: "word_overlap" as const,
    }));
    const result: SearchResult = {
      api_version: "1.0", search_id: entry.id, query, method: "word_overlap", reranker_enabled: false,
      score_type: "word_overlap", dataset_id: "legacy-demo", dataset_version: "1",
      pipeline_version: "word-overlap-v1", corpus_size: Math.max(500, entry.scopeCount),
      eligible_documents: entry.scopeCount, candidate_limit: Math.max(1, hits.length),
      candidate_count: hits.length, status: hits.length ? "results" : "empty",
      empty_reason: hits.length ? null : entry.scopeCount ? "no_candidates" : "filters_or_exclusions", hits,
    };
    return { id: entry.id, at: entry.at, query, result,
      view: { minimumScore: entry.view.minimum ? entry.view.minimum / 100 : null, limit: entry.view.limit } };
  });
  return librarySchema.parse({
    schema_version: 2,
    settings: { ...old.settings, department: old.settings.department || null },
    drafts: old.drafts.map((draft) => ({
      ...draft, query: convertQuery(draft.query), links: draft.links.map(getTopic),
    })),
    history,
  });
}

let database: IDBDatabase | null = null;
let memory = emptyLibrary();
let catalog = new Map<string, Topic>();
let warning = "";
let opening: Promise<void> | undefined;

async function readRecord(): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const transaction = database!.transaction("library", "readonly");
    const request = transaction.objectStore("library").get("state");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function initialize(): Promise<void> {
  try {
    database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("vkr-topic-catalog", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("library");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
      request.onblocked = () => reject(new Error("Storage blocked"));
    });
    database.onversionchange = () => {
      database?.close();
      database = null;
      warning = "Хранилище обновлено в другой вкладке. Обновите страницу для дальнейшего сохранения.";
    };
    const stored = await readRecord();
    if (stored && !librarySchema.safeParse(stored).success) {
      catalog = (await import("./demo")).demoTopicMap;
    }
    memory = migrateLibrary(stored, catalog);
  } catch {
    database?.close();
    database = null;
    warning = "Постоянное хранилище недоступно. Новые изменения сохраняются до обновления страницы. Ранее записанные данные остаются в браузере.";
  }
}

export async function readLibrary(): Promise<{ library: Library; warning: string }> {
  opening ??= initialize();
  await opening;
  if (database) memory = migrateLibrary(await readRecord(), catalog);
  return { library: structuredClone(memory), warning };
}

export async function updateLibrary(edit: (library: Library) => void): Promise<Library> {
  opening ??= initialize();
  await opening;
  if (!database) {
    const next = structuredClone(memory);
    edit(next);
    memory = librarySchema.parse(next);
    return structuredClone(memory);
  }
  return new Promise((resolve, reject) => {
    const transaction = database!.transaction("library", "readwrite");
    const store = transaction.objectStore("library");
    const request = store.get("state");
    let next: Library;
    let failure: unknown;
    request.onsuccess = () => {
      try {
        next = migrateLibrary(request.result, catalog);
        edit(next);
        next = librarySchema.parse(next);
        store.put(next, "state");
      } catch (error) {
        failure = error;
        transaction.abort();
      }
    };
    transaction.oncomplete = () => { memory = next; resolve(structuredClone(next)); };
    transaction.onabort = () => reject(failure ?? transaction.error ?? new Error("Не удалось сохранить данные."));
  });
}
