import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Badge, Button, Spinner } from "flowbite-react";
import { getAuthor } from "../api/client";
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

export default function AuthorPage() {
    const { olId } = useParams();
    const { info } = useInfo();
    const [author, setAuthor] = useState(null);
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);
    const [modalOpen, setModalOpen] = useState(false);

    useEffect(() => {
        setLoading(true);
        setNotFound(false);
        setAuthor(null);
        getAuthor(olId).then(
            (data) => {
                setAuthor(data);
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

    if (notFound || !author) {
        return <p className="text-red-500 font-medium">Author {olId} not found.</p>;
    }

    const photo = author.photos?.[0];

    return (
        <div>
            <Link to="/" className="text-sm text-blue-600 hover:underline">&larr; Back to search</Link>

            <div className="mt-4 flex flex-col md:flex-row gap-6">
                <img
                    className="object-contain h-56 w-40 bg-gray-100 rounded-full shadow-sm self-start"
                    src={photo ? `https://covers.openlibrary.org/a/id/${photo}-L.jpg` : "https://openlibrary.org/images/icons/avatar_author-sm.png"}
                    alt={author.name}
                    onError={(e) => { e.target.src = "https://openlibrary.org/images/icons/avatar_author-sm.png"; }}
                />

                <div className="flex-1">
                    <div className="flex items-start justify-between gap-4">
                        <h1 className="text-2xl font-bold">{author.name}</h1>
                        {author._override_status && <Badge color="info">override: {author._override_status}</Badge>}
                    </div>

                    {(author.birth_date || author.death_date) && (
                        <p className="text-gray-500 mt-1">
                            {author.birth_date || "?"} &ndash; {author.death_date || ""}
                        </p>
                    )}

                    {author.bio && <p className="text-gray-700 mt-2 whitespace-pre-line">{author.bio}</p>}

                    <dl className="mt-4 grid grid-cols-2 gap-x-4">
                        <Field label="OL ID" value={author.ol_id} />
                        <Field label="Alternate names" value={author.alternate_names} />
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
                entityType="authors"
                identifier={author.ol_id}
                record={author}
            />
        </div>
    );
}
