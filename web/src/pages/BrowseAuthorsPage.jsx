import { useEffect, useMemo, useState } from "react";
import { debounce } from "lodash";
import { TextInput, Select, Label, Checkbox } from "flowbite-react";
import Skeleton from "react-loading-skeleton";
import "react-loading-skeleton/dist/skeleton.css";
import { RiSortAsc } from "react-icons/ri";
import { Link } from "react-router-dom";
import { listAuthors } from "../api/client";
import PageNav from "../components/PageNav";
import { isBlank } from "../utils/isBlank";

export default function BrowseAuthorsPage() {
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [limit, setLimit] = useState(25);
    const [name, setName] = useState("");
    const [includeEmpty, setIncludeEmpty] = useState(false);
    const [sort, setSort] = useState("name");
    const [offset, setOffset] = useState(0);
    const [hasMore, setHasMore] = useState(false);

    const loadingPlaceholder = [0, 1, 2, 3, 4, 5];

    const runFetch = (params) => {
        setLoading(true);
        setError(null);

        listAuthors(params).then(
            (data) => {
                setResults(data.results || []);
                setHasMore(!!data.has_more);
                setLoading(false);
            },
            () => {
                setLoading(false);
                setError("Something went wrong while loading authors. Please try again.");
            }
        );
    };

    const debouncedFetch = useMemo(() => debounce((params) => runFetch(params), 400), []);

    useEffect(() => {
        setOffset(0);
        debouncedFetch({ limit, offset: 0, name: name || undefined, include_empty: includeEmpty || undefined, sort });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [limit, name, includeEmpty, sort]);

    const goToPage = (newOffset) => {
        setOffset(newOffset);
        runFetch({ limit, offset: newOffset, name: name || undefined, include_empty: includeEmpty || undefined, sort });
    };

    return (
        <div>
            <h1 className="text-xl font-bold pb-2">Browse Authors</h1>
            <p className="text-xs text-gray-400 pb-4">Browse all authors in the local index.</p>

            <div className="flex flex-col gap-3 bg-gray-50 p-4 rounded-lg border border-gray-200">
                <TextInput
                    id="name"
                    type="text"
                    placeholder="Filter by name..."
                    onChange={(e) => setName(e.target.value)}
                    value={name}
                />

                <div className="flex flex-wrap gap-4 items-center text-sm">
                    <div className="flex items-center gap-2">
                        <RiSortAsc className="text-gray-400" />
                        <Select sizing="sm" value={sort} onChange={(e) => setSort(e.target.value)}>
                            <option value="name">Name (A&ndash;Z)</option>
                            <option value="name_desc">Name (Z&ndash;A)</option>
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

                    <div className="flex items-center gap-2">
                        <Checkbox id="include_empty" checked={includeEmpty} onChange={(e) => setIncludeEmpty(e.target.checked)} />
                        <Label htmlFor="include_empty" value="Show unnamed/incomplete records" className="text-xs text-gray-500" />
                    </div>
                </div>
            </div>

            {error && <p className="pt-4 ml-2 text-red-500 font-medium">{error}</p>}

            <div className="mt-4 relative z-10 bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden">
                {loading ? (
                    loadingPlaceholder.map((_, i) => (
                        <div key={i} className="p-4 border-b last:border-0">
                            <Skeleton count={1} />
                        </div>
                    ))
                ) : results.length === 0 ? (
                    <p className="p-4 text-gray-500">No authors match these filters.</p>
                ) : (
                    results.map((author) => (
                        <div key={author.ol_id} className="p-4 border-b last:border-0 hover:bg-gray-50 transition-colors">
                            <Link to={`/author/${encodeURIComponent(author.ol_id)}`} className="group">
                                <p className="font-semibold text-blue-700 group-hover:underline">
                                    {isBlank(author.name) ? <span className="italic text-gray-400">(unnamed)</span> : author.name}
                                </p>
                            </Link>
                            {(author.birth_date || author.death_date) && (
                                <p className="text-sm text-gray-500">
                                    {author.birth_date || "?"} &ndash; {author.death_date || ""}
                                </p>
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
