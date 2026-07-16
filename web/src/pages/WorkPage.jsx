import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Badge, Button, Spinner } from "flowbite-react";
import { getWork, listWorkEditions } from "../api/client";
import { useInfo } from "../context/infoContext";
import SuggestEditModal from "../components/SuggestEditModal";
import PageNav from "../components/PageNav";

const EDITIONS_LIMIT = 10;

function Field({ label, value }) {
    if (value === undefined || value === null || value === "" || (Array.isArray(value) && value.length === 0)) return null;
    return (
        <div className="py-1">
            <dt className="text-xs uppercase tracking-wide text-gray-400">{label}</dt>
            <dd className="text-sm text-gray-800">{Array.isArray(value) ? value.join(", ") : value}</dd>
        </div>
    );
}

export default function WorkPage() {
    const { olId } = useParams();
    const { info } = useInfo();
    const [work, setWork] = useState(null);
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);

    const [editions, setEditions] = useState([]);
    const [editionsLoading, setEditionsLoading] = useState(false);
    const [editionsOffset, setEditionsOffset] = useState(0);
    const [editionsHasMore, setEditionsHasMore] = useState(false);

    useEffect(() => {
        setLoading(true);
        setNotFound(false);
        setWork(null);
        getWork(olId).then(
            (data) => {
                setWork(data);
                setLoading(false);
            },
            () => {
                setNotFound(true);
                setLoading(false);
            }
        );
    }, [olId]);

    const loadEditions = (offset) => {
        setEditionsLoading(true);
        listWorkEditions(olId, { limit: EDITIONS_LIMIT, offset }).then(
            (data) => {
                setEditions(data.results || []);
                setEditionsHasMore(!!data.has_more);
                setEditionsOffset(offset);
                setEditionsLoading(false);
            },
            () => setEditionsLoading(false)
        );
    };

    useEffect(() => {
        if (!work) return;
        loadEditions(0);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [work]);

    if (loading) {
        return (
            <div className="flex justify-center py-16">
                <Spinner size="xl" />
            </div>
        );
    }

    if (notFound || !work) {
        return <p className="text-red-500 font-medium">Work {olId} not found.</p>;
    }

    const cover = work.covers?.[0];

    return (
        <div>
            <Link to="/" className="text-sm text-blue-600 hover:underline">&larr; Back to search</Link>

            <div className="mt-4 flex flex-col md:flex-row gap-6">
                <img
                    className="object-contain h-56 w-40 bg-gray-100 rounded shadow-sm self-start"
                    src={cover ? `https://covers.openlibrary.org/b/id/${cover}-L.jpg` : "https://openlibrary.org/images/icons/avatar_book-sm.png"}
                    alt={work.title}
                    onError={(e) => { e.target.src = "https://openlibrary.org/images/icons/avatar_book-sm.png"; }}
                />

                <div className="flex-1">
                    <div className="flex items-start justify-between gap-4">
                        <h1 className="text-2xl font-bold">{work.title}</h1>
                        {work._override_status && <Badge color="info">override: {work._override_status}</Badge>}
                    </div>

                    {work.description && <p className="text-gray-700 mt-2 whitespace-pre-line">{work.description}</p>}

                    {work.authors?.length > 0 && (
                        <div className="mt-4">
                            <span className="text-xs uppercase tracking-wide text-gray-400">Authors</span>
                            <div className="flex gap-2 flex-wrap mt-1">
                                {work.authors.map((a) => (
                                    <Link key={a} to={`/author/${encodeURIComponent(a)}`}>
                                        <Badge color="gray">{a}</Badge>
                                    </Link>
                                ))}
                            </div>
                        </div>
                    )}

                    <dl className="mt-4 grid grid-cols-2 gap-x-4">
                        <Field label="OL ID" value={work.ol_id} />
                        <Field label="Subjects" value={work.subjects} />
                        <Field label="Subject people" value={work.subject_people} />
                        <Field label="Subject places" value={work.subject_places} />
                        <Field label="Series" value={work.series} />
                    </dl>

                    {info?.suggestions_enabled && (
                        <Button size="sm" className="mt-6" onClick={() => setModalOpen(true)}>
                            Suggest an edit
                        </Button>
                    )}
                </div>
            </div>

            <div className="mt-8">
                <h2 className="text-lg font-semibold mb-2">Editions</h2>
                {editionsLoading ? (
                    <div className="flex justify-center py-8">
                        <Spinner />
                    </div>
                ) : editions.length === 0 ? (
                    <p className="text-gray-500 text-sm">No editions found for this work.</p>
                ) : (
                    <div className="bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden">
                        {editions.map((e) => {
                            const isbn = e.isbn_13?.[0] || e.isbn_10?.[0] || null;
                            return (
                                <div key={e.ol_id} className="p-4 border-b last:border-0 hover:bg-gray-50 transition-colors">
                                    <div className="flex gap-4 items-center">
                                        <div className="flex-shrink-0">
                                            <img
                                                className="object-contain h-24 w-16 bg-gray-100 rounded shadow-sm"
                                                src={isbn ? `https://covers.openlibrary.org/b/isbn/${isbn}-M.jpg` : "https://openlibrary.org/images/icons/avatar_book-sm.png"}
                                                alt={e.title}
                                                onError={(ev) => { ev.target.src = "https://openlibrary.org/images/icons/avatar_book-sm.png"; }}
                                            />
                                        </div>
                                        <div className="flex-1">
                                            <Link to={`/edition/${encodeURIComponent(isbn || e.ol_id)}`} className="group">
                                                <p className="font-semibold text-blue-700 group-hover:underline">{e.title}</p>
                                                <p className="text-sm text-gray-500">
                                                    {e.physical_format || "Unknown format"}
                                                    {e.publish_date ? ` · ${e.publish_date}` : ""}
                                                </p>
                                                <p className="text-sm text-gray-500">ISBN: {isbn || "N/A"}</p>
                                            </Link>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
                {!editionsLoading && editions.length > 0 && (
                    <PageNav
                        offset={editionsOffset}
                        limit={EDITIONS_LIMIT}
                        hasMore={editionsHasMore}
                        resultCount={editions.length}
                        onPageChange={loadEditions}
                    />
                )}
            </div>

            <SuggestEditModal
                open={modalOpen}
                onClose={() => setModalOpen(false)}
                entityType="works"
                identifier={work.ol_id}
                record={work}
            />
        </div>
    );
}
