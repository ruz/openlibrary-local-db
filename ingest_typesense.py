import csv
import json
import os
import time
import typesense
from dotenv import load_dotenv

load_dotenv()

CSV_PATH = os.getenv("EDITIONS_CSV", "./data/processed/ol_dump_editions_2026-05-31.csv")
COLLECTION_ALIAS = "editions"
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 1000))
MAX_ROWS   = int(os.getenv("MAX_ROWS", 0)) or None  # 0 = unlimited

client = typesense.Client({
    "nodes": [{"host": os.getenv("TYPESENSE_HOST", "localhost"), "port": "8108", "protocol": "http"}],
    "api_key": os.getenv("TYPESENSE_API_KEY"),
    "connection_timeout_seconds": 100,
    "retry_interval_seconds": 60,
    "num_retries": 5
})

new_collection_name = f"editions_{int(time.time())}"

schema = {
    "name": new_collection_name,
    "fields": [
        {"name": "ol_id",        "type": "string"},
        {"name": "title",        "type": "string"},
        {"name": "author_names", "type": "string[]", "optional": True},
        {"name": "subjects",     "type": "string[]", "optional": True},
        {"name": "isbn_10",      "type": "string[]", "optional": True},
        {"name": "isbn_13",      "type": "string[]", "optional": True},
        {"name": "languages",    "type": "string[]",  "optional": True},
        {"name": "publish_date", "type": "int32"}
    ],
    "default_sorting_field": "publish_date"
}

print(f"Creating collection '{new_collection_name}'...")
client.collections.create(schema)


def parse_row(row):
    isbn_10 = json.loads(row["isbn_10"] or "[]")
    isbn_13 = json.loads(row["isbn_13"] or "[]")
    if not isbn_10 and not isbn_13:
        return None

    title = row["title"] or ""
    subtitle = row.get("subtitle") or ""
    if subtitle and subtitle not in ("None", ""):
        title = f"{title} - {subtitle}"

    return {
        "id":           row["ol_id"],
        "ol_id":        row["ol_id"],
        "title":        title,
        "author_names": json.loads(row["author_names"] or "[]"),
        "subjects":     json.loads(row["subjects"] or "[]"),
        "isbn_10":      isbn_10,
        "isbn_13":      isbn_13,
        "languages":    json.loads(row["languages"] or "[]"),
        "publish_date": int(row["publish_year"]) if row.get("publish_year") else 0
    }


print(f"Streaming '{CSV_PATH}' into Typesense...")
total = 0
errors = 0
batch = []

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=";", quotechar="|")

    for row in reader:
        if MAX_ROWS and total + len(batch) >= MAX_ROWS:
            break
        doc = parse_row(row)
        if not doc:
            continue
        batch.append(json.dumps(doc))

        if len(batch) >= BATCH_SIZE:
            raw_results = client.collections[new_collection_name].documents.import_(
                "\n".join(batch), {"action": "upsert"}
            )
            for line in raw_results.split("\n"):
                if not line:
                    continue
                parsed = json.loads(line)
                if not parsed.get("success"):
                    errors += 1
                    print(f"  Import error: {parsed}")

            total += len(batch)
            batch = []
            if total % 100_000 == 0:
                print(f"  {total:,} ingested, {errors} errors...")

if batch:
    raw_results = client.collections[new_collection_name].documents.import_(
        "\n".join(batch), {"action": "upsert"}
    )
    total += len(batch)

print(f"Ingestion complete: {total:,} records, {errors} errors.")

# Atomically flip alias — zero-downtime swap
old_collection_name = None
try:
    old_collection_name = client.aliases[COLLECTION_ALIAS].retrieve()["collection_name"]
except Exception:
    pass  # Alias doesn't exist yet on first run

print(f"Pointing alias '{COLLECTION_ALIAS}' → '{new_collection_name}'")
client.aliases.upsert(COLLECTION_ALIAS, {"collection_name": new_collection_name})

if old_collection_name:
    print(f"Deleting old collection '{old_collection_name}'")
    client.collections[old_collection_name].delete()

print("Done.")
