const BLANK_CHARS_RE = /[\s\x00-\x1f\x7f]+/g;

// Mirrors api/app.py's is_blank(): treats whitespace-only or control-byte-only
// strings (tabs, newlines, stray \x1a, etc, common in messy MARC-derived data)
// as blank, not just the empty string.
export function isBlank(value) {
    return !value || value.replace(BLANK_CHARS_RE, "") === "";
}
