import argparse
import csv
import ctypes as ct
import os
import json
import re
from datetime import date

DEFAULT_INPUT_PATH = "./data/unprocessed/"
DEFAULT_OUTPUT_PATH = "./data/processed/"

tasks = [
    {
        "file": "ol_dump_authors_2026-06-30.txt",
        "type": "authors",
        "fields": ["ol_id", "name", "birth_date", "death_date", "alternate_names", "bio", "photos"]
    },
    {
        "file": "ol_dump_works_2026-06-30.txt",
        "type": "works",
        "fields": ["ol_id", "title", "description", "authors", "subjects", "subject_people", "subject_places", "covers", "series"]
    },
    {
        "file": "ol_dump_editions_2026-06-30.txt",
        "type": "editions",
        "fields": ["ol_id", "title", "subtitle", "publish_date", "publish_year", "number_of_pages",
                   "physical_format", "publishers", "isbn_10", "isbn_13",
                   "subjects", "languages", "covers", "works", "authors", "author_names"]
    }
]

csv.field_size_limit(int(ct.c_ulong(-1).value // 2))

MIN_PLAUSIBLE_YEAR = 1000
MAX_PLAUSIBLE_YEAR = date.today().year + 1

# Global lookup dictionary
author_lookup = {}

def extract_year(date_str):
    """
    Extracts the first 4-digit year found in a string.
    Works for: 'December 31, 1993', '1555', '1973-1977', '(12 Jun. 2017)'
    Returns 0 if no plausible year can be found.
    """
    if not date_str or date_str == "None":
        return 0

    match = re.search(r'\b(14|15|16|17|18|19|20)\d{2}\b', date_str)

    if match:
        return int(match.group())

    match_loose = re.search(r'\d{4}', date_str)
    if match_loose:
        year = int(match_loose.group())
        if MIN_PLAUSIBLE_YEAR <= year <= MAX_PLAUSIBLE_YEAR:
            return year

    return 0

def format_list(data_list):
    """Returns empty JSON array string if list is empty."""
    if not data_list or len(data_list) == 0:
        return "[]"
    return json.dumps(data_list)

def clean(value):
    """Returns an empty string for missing/null values instead of a literal 'None'."""
    if value is None or value == "":
        return ""
    return value

def normalize_isbn(isbn):
    """Strips whitespace/hyphens and uppercases the check digit."""
    return isbn.replace("-", "").replace(" ", "").strip().upper()

def filter_image_ids(id_list):
    """Drops OpenLibrary's -1 'no image' placeholder from photo/cover id lists."""
    return [i for i in id_list if isinstance(i, int) and i > 0]

def main():
    parser = argparse.ArgumentParser(description="Process raw OpenLibrary dumps into CSV files.")
    parser.add_argument("--input-path", default=DEFAULT_INPUT_PATH,
                         help=f"Directory containing the raw dump files (default: {DEFAULT_INPUT_PATH})")
    parser.add_argument("--output-path", default=DEFAULT_OUTPUT_PATH,
                         help=f"Directory to write processed CSV files to (default: {DEFAULT_OUTPUT_PATH})")
    parser.add_argument("--limit", type=int, default=None,
                         help="Stop after processing this many data rows per input file (useful for smoke-testing on a sample)")
    args = parser.parse_args()

    for task in tasks:
        filename = task["file"]
        input_file = os.path.join(args.input_path, filename)
        output_file = os.path.join(args.output_path, filename.replace(".txt", ".csv"))

        if not os.path.exists(input_file):
            print(f"Skipping {filename}: File not found.")
            continue

        print(f"Processing {task['type']}...")

        rows_processed = 0
        rows_skipped = 0

        with open(output_file, "w", newline="", encoding="utf-8") as csv_out:
            writer = csv.DictWriter(csv_out, fieldnames=task["fields"], delimiter=";", quotechar="|")
            writer.writeheader()

            with open(input_file, "r", encoding="utf-8") as csv_in:
                reader = csv.reader(csv_in, delimiter="\t")

                for row in reader:
                    if args.limit is not None and rows_processed >= args.limit:
                        break

                    if len(row) > 4:
                        try:
                            data = json.loads(row[4])
                            out_row = {}

                            if task["type"] == "authors":
                                ol_id = row[1].replace("/authors/", "")
                                name = data.get("name")

                                if name:
                                    author_lookup[ol_id] = name

                                bio_data = data.get("bio", "")
                                bio_text = bio_data.get("value", "") if isinstance(bio_data, dict) else bio_data

                                out_row = {
                                    "ol_id": ol_id,
                                    "name": clean(name),
                                    "birth_date": clean(data.get("birth_date")),
                                    "death_date": clean(data.get("death_date")),
                                    "alternate_names": format_list(data.get("alternate_names")),
                                    "bio": clean(bio_text),
                                    "photos": format_list(filter_image_ids(data.get("photos", [])))
                                }
                            elif task["type"] == "works":
                                author_ids = []
                                for a in data.get("authors", []):
                                    if isinstance(a, dict) and isinstance(a.get("author"), dict):
                                        ak = a["author"].get("key", "")
                                        if ak: author_ids.append(ak.replace("/authors/", ""))
                                    elif isinstance(a, dict) and a.get("key"):
                                        ak = a.get("key", "")
                                        if ak: author_ids.append(ak.replace("/authors/", ""))

                                desc_data = data.get("description", "")
                                desc_text = desc_data.get("value", "") if isinstance(desc_data, dict) else desc_data

                                out_row = {
                                    "ol_id": row[1].replace("/works/", ""),
                                    "title": clean(data.get("title")),
                                    "description": clean(desc_text),
                                    "authors": format_list(author_ids),
                                    "subjects": format_list(data.get("subjects")),
                                    "subject_people": format_list(data.get("subject_people")),
                                    "subject_places": format_list(data.get("subject_places")),
                                    "covers": format_list(filter_image_ids(data.get("covers", []))),
                                    "series": format_list([s.get("series", {}).get("key", "").replace("/series/", "")
                                                          for s in data.get("series", [])
                                                          if isinstance(s, dict) and s.get("series")])
                                }
                            elif task["type"] == "editions":
                                author_ids = [a.get("key", "").replace("/authors/", "")
                                             for a in data.get("authors", [])
                                             if isinstance(a, dict) and a.get("key")]

                                names = [author_lookup[aid] for aid in author_ids if aid in author_lookup]

                                out_row = {
                                    "ol_id": row[1].replace("/books/", ""),
                                    "title": clean(data.get("title")),
                                    "subtitle": clean(data.get("subtitle")),
                                    "publish_date": clean(data.get("publish_date")),
                                    "publish_year": extract_year(data.get("publish_date", "")),
                                    "number_of_pages": clean(data.get("number_of_pages")),
                                    "physical_format": clean(data.get("physical_format")),
                                    "publishers": format_list(data.get("publishers")),
                                    "isbn_10": format_list([normalize_isbn(i) for i in data.get("isbn_10", [])]),
                                    "isbn_13": format_list([normalize_isbn(i) for i in data.get("isbn_13", [])]),
                                    "subjects": format_list(data.get("subjects")),
                                    "languages": format_list([l.get("key", "").replace("/languages/", "")
                                                             for l in data.get("languages", [])
                                                             if isinstance(l, dict) and l.get("key")]),
                                    "covers": format_list(filter_image_ids(data.get("covers", []))),
                                    "works": format_list([l.get("key", "").replace("/works/", "")
                                                             for l in data.get("works", [])
                                                             if isinstance(l, dict) and l.get("key")]),
                                    "authors": format_list(author_ids),
                                    "author_names": format_list(names)
                                }

                            writer.writerow(out_row)
                            rows_processed += 1
                        except (json.JSONDecodeError, TypeError):
                            rows_skipped += 1
                            continue

        print(f"{task['type']}: processed {rows_processed} rows, skipped {rows_skipped} malformed rows.")

    print("All tasks complete.")

if __name__ == "__main__":
    main()
