import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Badge, Button, Spinner } from "flowbite-react";
import { getWork } from "../api/client";
import { useInfo } from "../context/infoContext";
import SuggestEditModal from "../components/SuggestEditModal";

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
