import { readFile, stat, writeFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";

const source = process.argv[2];
if (!source) throw new Error("Укажите путь к JSON-каталогу или HTML-прототипу.");
const sourcePath = resolve(source);
if ((await stat(sourcePath)).size > 20 * 1024 * 1024) throw new Error("Файл превышает 20 МБ.");
const text = await readFile(sourcePath, "utf8");
if (Buffer.byteLength(text) > 20 * 1024 * 1024) throw new Error("Файл превышает 20 МБ.");
const embedded = text.match(/<script id="catalog" type="application\/json">([\s\S]*?)<\/script>/);
const input = JSON.parse(embedded ? embedded[1] : text.replace(/^\uFEFF/, ""));
const records = Array.isArray(input) ? input : input.topics;
if (!Array.isArray(records)) throw new Error("Ожидается массив тем.");
const seen = new Set();
const topics = records
  .filter((row) => !row.record_kind || row.record_kind === "real_public_metadata")
  .map((row) => {
    const id = String(row.id ?? "").trim();
    const title = typeof row.title === "string" ? row.title.trim() : "";
    if (!id || id.length > 128 || !title || title.length > 500 || seen.has(id)) {
      throw new Error("Требуются уникальный id и непустое название до 500 символов.");
    }
    seen.add(id);
    const metadata = row.metadata || row;
    const annotation = typeof row.annotation === "string" ? row.annotation.trim() || null : null;
    if (annotation && annotation.length > 12000) throw new Error("Описание превышает 12000 символов.");
    let sourceUrl = null;
    if (metadata.source_url) {
      const url = new URL(metadata.source_url);
      if (["http:", "https:"].includes(url.protocol) && !url.username && !url.password) sourceUrl = url.href;
    }
    return {
      id, title, annotation,
      annotation_origin: !annotation ? "missing" : row.annotation_origin ||
        (annotation.includes("автоматически сформирована") ? "generated" : "unknown"),
      metadata: {
        year: Number.isInteger(metadata.year) ? metadata.year : null,
        department: typeof metadata.department === "string" ? metadata.department : null,
        program: typeof metadata.program === "string" ? metadata.program : null,
        work_type: typeof metadata.work_type === "string" ? metadata.work_type : null,
        source_url: sourceUrl,
      },
    };
  });
if (!topics.length) throw new Error("Каталог пуст после отбора исходных записей.");
const dataset = {
  dataset_id: "demo-local",
  dataset_version: createHash("sha256").update(JSON.stringify(topics)).digest("hex").slice(0, 16),
  topics,
};
const destination = resolve(dirname(fileURLToPath(import.meta.url)), "../src/fixtures/catalog.local.json");
await writeFile(destination, JSON.stringify(dataset, null, 2) + "\n", "utf8");
console.log("Импортировано тем: " + topics.length);
