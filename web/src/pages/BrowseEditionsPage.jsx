import { useEffect, useMemo, useState } from "react";
import { debounce } from "lodash";
import { TextInput, Select, Label } from "flowbite-react";
import Skeleton from "react-loading-skeleton";
import "react-loading-skeleton/dist/skeleton.css";
import { RiFilter3Line, RiSortAsc } from "react-icons/ri";
import { Link } from "react-router-dom";
import languages from "../languages.json";
import { listEditions } from "../api/client";
import PageNav from "../components/PageNav";

function resultToItem(item, i, offset) {
    const isbn = item.isbn_13?.[0] || item.isbn_10?.[0] || null;
    return {
        id: offset + i,
        title: item.title,
        isbn,
        olId: item.ol_id,
        author: item.author_names?.[0] || "Unknown Author",
    };
}

export default function BrowseEditionsPage() {
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [limit, setLimit] = useState(25);
    const [lang, setLang] = useState("");
    const [format, setFormat] = useState("");
    const [yearMin, setYearMin] = useState("");
    const [yearMax, setYearMax] = useState("");
    const [title, setTitle] = useState("");
    const [sort, setSort] = useState("title");
    const [offset, setOffset] = useState(0);
    const [hasMore, setHasMore] = useState(false);

    const loadingPlaceholder = [0, 1, 2, 3, 4, 5];

    const runFetch = (params) => {
        setLoading(true);
        setError(null);

        listEditions(params).then(
            (data) => {
                setResults((data.results || []).map((item, i) => resultToItem(item, i, params.offset)));
                setHasMore(!!data.has_more);
                setLoading(false);
            },
            () => {
                setLoading(false);
                setError("Something went wrong while loading editions. Please try again.");
            }
        );
    };

    const debouncedFetch = useMemo(() => debounce((params) => runFetch(params), 400), []);

    useEffect(() => {
        setOffset(0);
        debouncedFetch({
            limit,
            offset: 0,
            lang: lang || undefined,
            format: format || undefined,
            year_min: yearMin || undefined,
            year_max: yearMax || undefined,
            title: title || undefined,
            sort,
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [limit, lang, format, yearMin, yearMax, title, sort]);

    const goToPage = (newOffset) => {
        setOffset(newOffset);
        runFetch({
            limit,
            offset: newOffset,
            lang: lang || undefined,
            format: format || undefined,
            year_min: yearMin || undefined,
            year_max: yearMax || undefined,
            title: title || undefined,
            sort,
        });
    };

    return (
        <div>
            <h1 className="text-xl font-bold pb-2">Browse Editions</h1>
            <p className="text-xs text-gray-400 pb-4">Browse all editions in the local index.</p>

            <div className="flex flex-col gap-3 bg-gray-50 p-4 rounded-lg border border-gray-200">
                <TextInput
                    id="title"
                    type="text"
                    placeholder="Filter by title..."
                    onChange={(e) => setTitle(e.target.value)}
                    value={title}
                />

                <div className="flex flex-wrap gap-4 items-center text-sm">
                    <div className="flex items-center gap-2">
                        <RiFilter3Line className="text-gray-400" />
                        <Select sizing="sm" value={lang} onChange={(e) => setLang(e.target.value)}>
                            <option value="">Any language</option>
                            {languages.map((l) => (
                                <option key={l.code} value={l.code}>
                                    {l.name}
                                </option>
                            ))}
                        </Select>
                    </div>

                    <TextInput
                        sizing="sm"
                        type="text"
                        placeholder="Format (e.g. Hardcover)"
                        onChange={(e) => setFormat(e.target.value)}
                        value={format}
                    />

                    <div className="flex items-center gap-2">
                        <Label htmlFor="year_min" value="Year:" className="text-xs text-gray-500" />
                        <TextInput
                            sizing="sm"
                            id="year_min"
                            type="number"
                            placeholder="Min"
                            className="w-24"
                            onChange={(e) => setYearMin(e.target.value)}
                            value={yearMin}
                        />
                        <span className="text-gray-400">&ndash;</span>
                        <TextInput
                            sizing="sm"
                            type="number"
                            placeholder="Max"
                            className="w-24"
                            onChange={(e) => setYearMax(e.target.value)}
                            value={yearMax}
                        />
                    </div>

                    <div className="flex items-center gap-2">
                        <RiSortAsc className="text-gray-400" />
                        <Select sizing="sm" value={sort} onChange={(e) => setSort(e.target.value)}>
                            <option value="title">Title (A&ndash;Z)</option>
                            <option value="title_desc">Title (Z&ndash;A)</option>
                            <option value="newest">Newest</option>
                            <option value="oldest">Oldest</option>
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
                            <div className="flex gap-4">
                                <Skeleton height={96} width={64} />
                                <div className="flex-1">
                                    <Skeleton count={2} />
                                </div>
                            </div>
                        </div>
                    ))
                ) : results.length === 0 ? (
                    <p className="p-4 text-gray-500">No editions match these filters.</p>
                ) : (
                    results.map((data) => (
                        <div key={data.id} className="p-4 border-b last:border-0 hover:bg-gray-50 transition-colors">
                            <div className="flex gap-4 items-center">
                                <div className="flex-shrink-0">
                                    <img
                                        className="object-contain h-24 w-16 bg-gray-100 rounded shadow-sm"
                                        src={data.isbn ? `https://covers.openlibrary.org/b/isbn/${data.isbn}-M.jpg` : "https://openlibrary.org/images/icons/avatar_book-sm.png"}
                                        alt={data.title}
                                        onError={(e) => { e.target.src = "https://openlibrary.org/images/icons/avatar_book-sm.png"; }}
                                    />
                                </div>
                                <div className="flex-1">
                                    <Link to={`/edition/${encodeURIComponent(data.isbn || data.olId)}`} className="group">
                                        <p className="font-semibold text-blue-700 group-hover:underline">{data.title}</p>
                                        <p className="text-sm text-gray-700 font-medium">by {data.author}</p>
                                        <p className="text-sm text-gray-500">ISBN: {data.isbn || "N/A"}</p>
                                    </Link>
                                </div>
                            </div>
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
