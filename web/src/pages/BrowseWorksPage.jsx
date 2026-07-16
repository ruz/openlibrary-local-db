import { useEffect, useMemo, useState } from "react";
import { debounce } from "lodash";
import { TextInput, Select, Label } from "flowbite-react";
import Skeleton from "react-loading-skeleton";
import "react-loading-skeleton/dist/skeleton.css";
import { RiSortAsc } from "react-icons/ri";
import { Link } from "react-router-dom";
import { listWorks } from "../api/client";
import PageNav from "../components/PageNav";

export default function BrowseWorksPage() {
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [limit, setLimit] = useState(25);
    const [subject, setSubject] = useState("");
    const [title, setTitle] = useState("");
    const [sort, setSort] = useState("title");
    const [offset, setOffset] = useState(0);
    const [hasMore, setHasMore] = useState(false);

    const loadingPlaceholder = [0, 1, 2, 3, 4, 5];

    const runFetch = (params) => {
        setLoading(true);
        setError(null);

        listWorks(params).then(
            (data) => {
                setResults(data.results || []);
                setHasMore(!!data.has_more);
                setLoading(false);
            },
            () => {
                setLoading(false);
                setError("Something went wrong while loading works. Please try again.");
            }
        );
    };

    const debouncedFetch = useMemo(() => debounce((params) => runFetch(params), 400), []);

    useEffect(() => {
        setOffset(0);
        debouncedFetch({
            limit,
            offset: 0,
            subject: subject || undefined,
            title: title || undefined,
            sort,
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [limit, subject, title, sort]);

    const goToPage = (newOffset) => {
        setOffset(newOffset);
        runFetch({
            limit,
            offset: newOffset,
            subject: subject || undefined,
            title: title || undefined,
            sort,
        });
    };

    return (
        <div>
            <h1 className="text-xl font-bold pb-2">Browse Works</h1>
            <p className="text-xs text-gray-400 pb-4">Browse all works in the local index.</p>

            <div className="flex flex-col gap-3 bg-gray-50 p-4 rounded-lg border border-gray-200">
                <TextInput
                    id="title"
                    type="text"
                    placeholder="Filter by title..."
                    onChange={(e) => setTitle(e.target.value)}
                    value={title}
                />

                <div className="flex flex-wrap gap-4 items-center text-sm">
                    <TextInput
                        sizing="sm"
                        type="text"
                        placeholder="Subject (e.g. Fiction)"
                        onChange={(e) => setSubject(e.target.value)}
                        value={subject}
                    />

                    <div className="flex items-center gap-2">
                        <RiSortAsc className="text-gray-400" />
                        <Select sizing="sm" value={sort} onChange={(e) => setSort(e.target.value)}>
                            <option value="title">Title (A&ndash;Z)</option>
                            <option value="title_desc">Title (Z&ndash;A)</option>
                        </Select>
                    </div>

                    <div className="flex items-center gap-2">
                        <Label htmlFor="limit" value="Limit:" className="text-xs text-gray-500" />
                        <Select sizing="sm" id="limit" value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                            <option value={10}>10</option>
                            <option value={25}>25</option>
                            <option value={50}>50</option>
                        </Select>
                    </div>
                </div>
            </div>

            {error && <p className="pt-4 ml-2 text-red-500 font-medium">{error}</p>}

            <div className="mt-4 relative z-10 bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden">
                {loading ? (
                    loadingPlaceholder.map((_, i) => (
                        <div key={i} className="p-4 border-b last:border-0">
                            <Skeleton count={2} />
                        </div>
                    ))
                ) : results.length === 0 ? (
                    <p className="p-4 text-gray-500">No works match these filters.</p>
                ) : (
                    results.map((work) => (
                        <div key={work.ol_id} className="p-4 border-b last:border-0 hover:bg-gray-50 transition-colors">
                            <Link to={`/work/${encodeURIComponent(work.ol_id)}`} className="group">
                                <p className="font-semibold text-blue-700 group-hover:underline">{work.title}</p>
                            </Link>
                            {work.subjects?.length > 0 && (
                                <p className="text-sm text-gray-500 truncate">{work.subjects.slice(0, 5).join(", ")}</p>
                            )}
                        </div>
                    ))
                )}
            </div>

            {!loading && (
                <PageNav offset={offset} limit={limit} hasMore={hasMore} resultCount={results.length} onPageChange={goToPage} />
            )}
        </div>
    );
}
