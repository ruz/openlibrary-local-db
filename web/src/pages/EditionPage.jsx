import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Badge, Button, Spinner } from "flowbite-react";
import { getEdition } from "../api/client";
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

export default function EditionPage() {
    const { identifier } = useParams();
    const { info } = useInfo();
    const [edition, setEdition] = useState(null);
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);

    useEffect(() => {
        setLoading(true);
        setNotFound(false);
        setEdition(null);
        getEdition(identifier).then(
            (data) => {
                setEdition(data);
                setLoading(false);
            },
            () => {
                setNotFound(true);
                setLoading(false);
            }
        );
    }, [identifier]);

    if (loading) {
        return (
            <div className="flex justify-center py-16">
                <Spinner size="xl" />
            </div>
        );
    }

    if (notFound || !edition) {
        return <p className="text-red-500 font-medium">Edition {identifier} not found.</p>;
    }

    const isbn = edition.isbn_13?.[0] || edition.isbn_10?.[0];

    return (
        <div>
            <Link to="/" className="text-sm text-blue-600 hover:underline">&larr; Back to search</Link>

            <div className="mt-4 flex flex-col md:flex-row gap-6">
                <img
                    className="object-contain h-56 w-40 bg-gray-100 rounded shadow-sm self-start"
                    src={isbn ? `https://covers.openlibrary.org/b/isbn/${isbn}-L.jpg` : "https://openlibrary.org/images/icons/avatar_book-sm.png"}
                    alt={edition.title}
                    onError={(e) => { e.target.src = "https://openlibrary.org/images/icons/avatar_book-sm.png"; }}
                />

                <div className="flex-1">
                    <div className="flex items-start justify-between gap-4">
                        <div>
                            <h1 className="text-2xl font-bold">{edition.title}</h1>
                            {edition.subtitle && <p className="text-gray-500">{edition.subtitle}</p>}
                            {edition.author_names?.length > 0 && (
                                <p className="text-gray-700 mt-1">
                                    by{" "}
                                    {edition.author_names.map((name, i) => (
                                        <span key={name}>
                                            {edition.authors?.[i] ? (
                                                <Link to={`/author/${encodeURIComponent(edition.authors[i])}`} className="text-blue-600 hover:underline">
                                                    {name}
                                                </Link>
                                            ) : name}
                                            {i < edition.author_names.length - 1 ? ", " : ""}
                                        </span>
                                    ))}
                                </p>
                            )}
                        </div>
                        {edition._override_status && <Badge color="info">override: {edition._override_status}</Badge>}
                    </div>

                    <dl className="mt-4 grid grid-cols-2 gap-x-4">
                        <Field label="OL ID" value={edition.ol_id} />
                        <Field label="Publish date" value={edition.publish_date} />
                        <Field label="Publish year" value={edition.publish_year} />
                        <Field label="Pages" value={edition.number_of_pages} />
                        <Field label="Format" value={edition.physical_format} />
                        <Field label="Publishers" value={edition.publishers} />
                        <Field label="ISBN-10" value={edition.isbn_10} />
                        <Field label="ISBN-13" value={edition.isbn_13} />
                        <Field label="Languages" value={edition.languages} />
                        <Field label="Subjects" value={edition.subjects} />
                    </dl>

                    {edition.works?.length > 0 && (
                        <div className="mt-4">
                            <span className="text-xs uppercase tracking-wide text-gray-400">Part of work</span>
                            <div className="flex gap-2 flex-wrap mt-1">
                                {edition.works.map((w) => (
                                    <Link key={w} to={`/work/${encodeURIComponent(w)}`}>
                                        <Badge color="gray">{w}</Badge>
                                    </Link>
                                ))}
                            </div>
                        </div>
                    )}

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
                entityType="editions"
                identifier={edition.ol_id}
                record={edition}
            />
        </div>
    );
}
