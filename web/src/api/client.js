import axios from "axios";

const client = axios.create({
    baseURL: import.meta.env.VITE_API_URL,
});

export function getInfo() {
    return client.get("v1/info").then((r) => r.data);
}

export function search(query, { limit, offset, lang, sort } = {}) {
    return client
        .get(`v1/search/${encodeURIComponent(query)}`, { params: { limit, offset, lang, sort } })
        .then((r) => r.data);
}

export function listEditions({ limit, offset, lang, format, year_min, year_max, title, include_empty, sort } = {}) {
    return client
        .get("v1/editions", { params: { limit, offset, lang, format, year_min, year_max, title, include_empty, sort } })
        .then((r) => r.data);
}

export function listWorks({ limit, offset, subject, title, include_empty, sort } = {}) {
    return client
        .get("v1/works", { params: { limit, offset, subject, title, include_empty, sort } })
        .then((r) => r.data);
}

export function listAuthors({ limit, offset, name, include_empty, sort } = {}) {
    return client
        .get("v1/authors", { params: { limit, offset, name, include_empty, sort } })
        .then((r) => r.data);
}

export function listWorkEditions(workOlId, { limit, offset, sort } = {}) {
    return client
        .get(`v1/work/${encodeURIComponent(workOlId)}/editions`, { params: { limit, offset, sort } })
        .then((r) => r.data);
}

export function listAuthorWorks(authorOlId, { limit, offset, sort } = {}) {
    return client
        .get(`v1/author/${encodeURIComponent(authorOlId)}/works`, { params: { limit, offset, sort } })
        .then((r) => r.data);
}

export function getEdition(identifier) {
    return client.get(`v1/edition/${encodeURIComponent(identifier)}`).then((r) => r.data);
}

export function getWork(olId) {
    return client.get(`v1/work/${encodeURIComponent(olId)}`).then((r) => r.data);
}

export function getAuthor(olId) {
    return client.get(`v1/author/${encodeURIComponent(olId)}`).then((r) => r.data);
}

// entityRoute: "edition" | "work" | "author"
export function suggestEdit(entityRoute, identifier, body) {
    return client
        .post(`v1/${entityRoute}/${encodeURIComponent(identifier)}/suggest`, body)
        .then((r) => r.data);
}

export function listSuggestions(token, { status, entity_type } = {}) {
    return client
        .get("v1/suggestions", { params: { status, entity_type }, headers: { "X-Edit-Token": token } })
        .then((r) => r.data);
}

export function approveSuggestion(token, id) {
    return client
        .post(`v1/suggestions/${id}/approve`, {}, { headers: { "X-Edit-Token": token } })
        .then((r) => r.data);
}

export function rejectSuggestion(token, id) {
    return client
        .post(`v1/suggestions/${id}/reject`, {}, { headers: { "X-Edit-Token": token } })
        .then((r) => r.data);
}

export default client;
