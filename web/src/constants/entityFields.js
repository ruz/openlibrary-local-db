// Mirrors api/app.py's *_PATCHABLE_FIELDS / *_JSON_FIELDS. Keep in sync with the backend.
export const ENTITY_FIELD_CONFIG = {
    editions: {
        route: "edition",
        label: "Edition",
        fields: [
            { name: "title", label: "Title", type: "text" },
            { name: "subtitle", label: "Subtitle", type: "text" },
            { name: "publish_date", label: "Publish date", type: "text" },
            { name: "publish_year", label: "Publish year", type: "number" },
            { name: "number_of_pages", label: "Number of pages", type: "number" },
            { name: "physical_format", label: "Physical format", type: "text" },
            { name: "publishers", label: "Publishers", type: "json" },
            { name: "isbn_10", label: "ISBN-10", type: "json" },
            { name: "isbn_13", label: "ISBN-13", type: "json" },
            { name: "subjects", label: "Subjects", type: "json" },
            { name: "languages", label: "Languages", type: "json" },
            { name: "authors", label: "Author IDs", type: "json" },
            { name: "author_names", label: "Author names", type: "json" },
            { name: "works", label: "Work IDs", type: "json" },
        ],
    },
    works: {
        route: "work",
        label: "Work",
        fields: [
            { name: "title", label: "Title", type: "text" },
            { name: "description", label: "Description", type: "textarea" },
            { name: "authors", label: "Author IDs", type: "json" },
            { name: "subjects", label: "Subjects", type: "json" },
            { name: "subject_people", label: "Subject people", type: "json" },
            { name: "subject_places", label: "Subject places", type: "json" },
            { name: "covers", label: "Cover IDs", type: "json" },
            { name: "series", label: "Series", type: "json" },
        ],
    },
    authors: {
        route: "author",
        label: "Author",
        fields: [
            { name: "name", label: "Name", type: "text" },
            { name: "birth_date", label: "Birth date", type: "text" },
            { name: "death_date", label: "Death date", type: "text" },
            { name: "bio", label: "Bio", type: "textarea" },
            { name: "alternate_names", label: "Alternate names", type: "json" },
            { name: "photos", label: "Photo IDs", type: "json" },
        ],
    },
};
