import csv
import ctypes as ct
import os
import json
import re

INPUT_PATH = "./data/unprocessed/"
OUTPUT_PATH = "./data/processed/"

tasks = [
    {
        "file": "ol_dump_authors_2026-05-31.txt",
        "type": "authors",
        "fields": ["ol_id", "name", "birth_date", "death_date", "alternate_names", "bio", "photos"]
    },
    {
        "file": "ol_dump_works_2026-05-31.txt",
        "type": "works",
        "fields": ["ol_id", "title", "description", "authors", "subjects", "subject_people", "subject_places", "covers", "series"]
    },
    {
        "file": "ol_dump_editions_2026-05-31.txt",
        "type": "editions",
        "fields": ["ol_id", "title", "subtitle", "publish_date", "publish_year", "number_of_pages", 
                   "physical_format", "publishers", "isbn_10", "isbn_13", 
                   "subjects", "languages", "covers", "works", "authors", "author_names"]
    }
]

csv.field_size_limit(int(ct.c_ulong(-1).value // 2))

# Global lookup dictionary
author_lookup = {}

def extract_year(date_str):
    """
    Extracts the first 4-digit year found in a string.
    Works for: 'December 31, 1993', '1555', '1973-1977', '(12 Jun. 2017)'
    """
    if not date_str or date_str == "None":
        return 0
    
    match = re.search(r'\b(14|15|16|17|18|19|20)\d{2}\b', date_str)
    
    if match:
        return int(match.group())
    
    match_loose = re.search(r'\d{4}', date_str)
    if match_loose:
        return int(match_loose.group())
        
    return 0

def format_list(data_list):
    """Returns empty JSON array string if list is empty."""
    if not data_list or len(data_list) == 0:
        return "[]"
    return json.dumps(data_list)

for task in tasks:
    filename = task["file"]
    input_file = os.path.join(INPUT_PATH, filename)
    output_file = os.path.join(OUTPUT_PATH, filename.replace(".txt", ".csv"))
    
    if not os.path.exists(input_file):
        print(f"Skipping {filename}: File not found.")
        continue

    print(f"Processing {task['type']}...")

    with open(output_file, "w", newline="", encoding="utf-8") as csv_out:
        writer = csv.DictWriter(csv_out, fieldnames=task["fields"], delimiter=";", quotechar="|")
        writer.writeheader()

        with open(input_file, "r", encoding="utf-8") as csv_in:
            reader = csv.reader(csv_in, delimiter="\t")
            
            for row in reader:
                if len(row) > 4:
                    try:
                        data = json.loads(row[4])
                        out_row = {}

                        if task["type"] == "authors":
                            ol_id = row[1].replace("/authors/", "")
                            name = data.get("name", "None")
                            
                            author_lookup[ol_id] = name

                            bio_data = data.get("bio", "")
                            bio_text = bio_data.get("value", "") if isinstance(bio_data, dict) else bio_data

                            out_row = {
                                "ol_id": ol_id,
                                "name": name,
                                "birth_date": data.get("birth_date", "None"),
                                "death_date": data.get("death_date", "None"),
                                "alternate_names": format_list(data.get("alternate_names")),
                                "bio": bio_text if bio_text else "None",
                                "photos": format_list(data.get("photos"))
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
                                "title": data.get("title", "None"),
                                "description": desc_text if desc_text else "None",
                                "authors": format_list(author_ids),
                                "subjects": format_list(data.get("subjects")),
                                "subject_people": format_list(data.get("subject_people")),
                                "subject_places": format_list(data.get("subject_places")),
                                "covers": format_list(data.get("covers")),
                                "series": format_list([s.get("series", {}).get("key", "").replace("/series/", "") 
                                                      for s in data.get("series", []) 
                                                      if isinstance(s, dict) and s.get("series")])
                            }
                        elif task["type"] == "editions":
                            author_ids = [a.get("key", "").replace("/authors/", "") 
                                         for a in data.get("authors", []) 
                                         if isinstance(a, dict) and a.get("key")]
                            
                            names = [author_lookup.get(aid) for aid in author_ids if aid in author_lookup]
                            
                            out_row = {
                                "ol_id": row[1].replace("/books/", ""),
                                "title": data.get("title", "None"),
                                "subtitle": data.get("subtitle", "None"),
                                "publish_date": data.get("publish_date", "None"),
                                "publish_year": extract_year(data.get("publish_date", "None")),
                                "number_of_pages": data.get("number_of_pages", "None"),
                                "physical_format": data.get("physical_format", "None"),
                                "publishers": format_list(data.get("publishers")),
                                "isbn_10": format_list(data.get("isbn_10")),
                                "isbn_13": format_list(data.get("isbn_13")),
                                "subjects": format_list(data.get("subjects")),
                                "languages": format_list([l.get("key", "").replace("/languages/", "") 
                                                         for l in data.get("languages", []) 
                                                         if isinstance(l, dict) and l.get("key")]),
                                "covers": format_list(data.get("covers")),
                                "works": format_list([l.get("key", "").replace("/works/", "") 
                                                         for l in data.get("works", []) 
                                                         if isinstance(l, dict) and l.get("key")]),
                                "authors": format_list(author_ids),
                                "author_names": format_list(names)
                            }

                        writer.writerow(out_row)
                    except (json.JSONDecodeError, TypeError):
                        continue

print("All tasks complete.")