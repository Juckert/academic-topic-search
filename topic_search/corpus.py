"""Map external JSON, JSONL or CSV records to a validated topic corpus."""

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

ANNOTATION_ORIGINS = ("original", "generated", "unknown", "missing")


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    text: str
    metadata: dict
    annotation: str | None = None
    annotation_origin: str = "missing"


@dataclass(frozen=True)
class Corpus:
    topics: tuple
    metadata_fields: tuple
    input_count: int
    excluded_count: int


def from_records(records, config):
    if any(not isinstance(config.get(field),str) or not config[field].strip() for field in ("id_field","title_field")):
        raise ValueError("id_field and title_field must be nonempty source field names")
    if not isinstance(records, list) or not records:
        raise ValueError("Corpus must contain a nonempty list of records")
    metadata_fields = config.get("metadata_fields", {})
    record_filter = config.get("record_filter", {})
    if not isinstance(metadata_fields, dict) or any(not isinstance(v, str) for v in metadata_fields.values()):
        raise ValueError("metadata_fields must map public names to source field names")
    if not isinstance(record_filter, dict) or any(not isinstance(v, list) or not v for v in record_filter.values()):
        raise ValueError("record_filter must map fields to nonempty lists of allowed values")
    if type(config.get("include_annotation", False)) is not bool:
        raise ValueError("include_annotation must be boolean")
    topics, seen, excluded = [], set(), 0
    for number, row in enumerate(records, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Record {number}: object required")
        if any(key not in row for key in record_filter):
            raise ValueError(f"Record {number}: configured record-filter field missing")
        if any(row[key] not in values for key, values in record_filter.items()):
            excluded += 1
            continue
        doc_id, title = row.get(config["id_field"]), row.get(config["title_field"])
        if type(doc_id) not in (str, int) or not str(doc_id).strip():
            raise ValueError(f"Record {number}: nonempty string/integer ID required")
        doc_id = str(doc_id).strip()
        if doc_id in seen:
            raise ValueError(f"Record {number}: duplicate ID {doc_id}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Record {number}: nonempty title required")
        seen.add(doc_id)
        title = title.strip()
        text = title
        # The annotation is read for display whenever annotation_field is set;
        # include_annotation only controls whether it is indexed.
        annotation, origin = None, "missing"
        if config.get("include_annotation", False) and not config.get("annotation_field"):
            raise ValueError("annotation_field required when include_annotation=true")
        if config.get("annotation_field"):
            annotation = row.get(config["annotation_field"])
            if annotation is not None and not isinstance(annotation, str):
                raise ValueError(f"Record {number}: annotation must be a string or null")
            annotation = annotation.strip() if annotation and annotation.strip() else None
        if annotation is not None:
            origin = row.get(config["annotation_origin_field"]) if config.get("annotation_origin_field") else None
            if origin in (None, "", "missing"):
                origin = "unknown"
            if origin not in ANNOTATION_ORIGINS:
                raise ValueError(f"Record {number}: annotation origin must be one of {', '.join(ANNOTATION_ORIGINS)}")
            if config.get("include_annotation", False):
                text += "\n\n" + annotation
        metadata = {name:row.get(source) for name,source in metadata_fields.items()}
        if any(v is not None and type(v) not in (str,int,float,bool) for v in metadata.values()):
            raise ValueError(f"Record {number}: metadata values must be scalar or null")
        if any(type(v) is float and not math.isfinite(v) for v in metadata.values()):
            raise ValueError(f"Record {number}: metadata numbers must be finite")
        topics.append(Topic(doc_id, title, text, metadata, annotation, origin))
    if not topics:
        raise ValueError("No records remain after corpus filtering")
    return Corpus(tuple(topics), tuple(metadata_fields), len(records), excluded)


def load_corpus(config, root):
    path = Path(root) / config["path"]
    suffix = path.suffix.lower()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if suffix == ".json":
            records = json.load(stream)
            if config.get("records_key"):
                if not isinstance(records, dict) or config["records_key"] not in records:
                    raise ValueError("Configured records_key missing from JSON object")
                records = records[config["records_key"]]
        elif suffix in (".jsonl", ".ndjson"):
            records = [json.loads(line) for line in stream if line.strip()]
        elif suffix == ".csv":
            reader = csv.DictReader(stream, delimiter=config.get("delimiter", ","))
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("CSV needs unique column names")
            records = list(reader)
            if any(None in row for row in records):
                raise ValueError("CSV row contains more values than the header")
        else:
            raise ValueError("Supported corpus formats: JSON, JSONL, CSV")
    return from_records(records, config)
