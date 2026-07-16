import { useEffect, useMemo, useState } from "react";
import { debounce } from "lodash";
import { TextInput, Select, Label } from "flowbite-react";
import Skeleton from "react-loading-skeleton";
import "react-loading-skeleton/dist/skeleton.css";
import { RiSearch2Line, RiFilter3Line, RiSortAsc } from "react-icons/ri";
import { Link } from "react-router-dom";
import languages from "../languages.json";
import { search } from "../api/client";
import { useInfo } from "../context/infoContext";
import PageNav from "../components/PageNav";

function resultToItem(item, i, offset) {
    const isbn = item.isbn_13?.[0] || item.isbn_10?.[0] || null;
    return {
        id: offset + i,
        title: item.title,
        isbn,
        author: item.author_names?.[0] || "Unknown Author",
    };
}

export default function SearchPage() {
    const { info } = useInfo();
    const [searchTerm, setSearchTerm] = useState("");
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showList, setShowList] = useState(false);
    const [notFound, setNotFound] = useState(false);
    const [error, setError] = useState(null);
    const [limit, setLimit] = useState(10);
    const [lang, setLang] = useState("eng");
    const [sort, setSort] = useState("relevance");
    const [offset, setOffset] = useState(0);
    const [hasMore, setHasMore] = useState(false);

    const loadingPlaceholder = [0, 1, 2, 3, 4, 5];

    const runSearch = (term, params) => {
        if (!term) return;

        setLoading(true);
        setNotFound(false);
        setError(null);

        search(term, params).then(
            (data) => {
                setResults((data.results || []).map((item, i) => resultToItem(item, i, params.offset)));
                setHasMore(!!data.has_more);
                setLoading(false);
                setShowList(true);
            },
            (err) => {
                setLoading(false);
                if (err.response?.status === 404) {
                    setResults([]);
                    setShowList(false);
                    setHasMore(false);
                    setNotFound(true);
                } else {
                    setShowList(false);
                    setError("Something went wrong while searching. Please try again.");
                }
            }
        );
    };

    const debouncedFetch = useMemo(
        () => debounce((term, params) => runSearch(term, params), 400),
        []
    );

    // New search term / filter change: reset to page 1.
    useEffect(() => {
        if (searchTerm.trim() === "") {
            setResults([]);
            setShowList(false);
            setNotFound(false);
            setError(null);
            return;
        }
        setOffset(0);
        debouncedFetch(searchTerm, { limit, offset: 0, lang, sort });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [searchTerm, limit, lang, sort]);

    const goToPage = (newOffset) => {
        setOffset(newOffset);
        runSearch(searchTerm, { limit, offset: newOffset, lang, sort });
    };

    return (
        <div>
            <h1 className="text-xl font-bold pb-2">OpenLibrary Local Search</h1>
            {info && (
                <p className="text-xs text-gray-400 pb-4">
                    Searching a local index of OpenLibrary editions{info.oldump_date ? ` (dump: ${info.oldump_date})` : ""}.
                </p>
            )}

            <div className="flex flex-col gap-3 bg-gray-50 p-4 rounded-lg border border-gray-200">
                <TextInput
                    icon={RiSearch2Line}
                    id="search"
                    type="text"
                    placeholder="Search by book title or isbn..."
                    onChange={(e) => setSearchTerm(e.target.value)}
                    value={searchTerm}
                />

                <div className="flex flex-wrap gap-4 items-center text-sm">
                    <div className="flex items-center gap-2">
                        <RiFilter3Line className="text-gray-400" />
                        <Select sizing="sm" value={lang} onChange={(e) => setLang(e.target.value)}>
                            {languages.map((l) => (
                                <option key={l.code} value={l.code}>
                                    {l.name}
                                </option>
                            ))}
                        </Select>
                    </div>

                    <div className="flex items-center gap-2">
                        <RiSortAsc className="text-gray-400" />
                        <Select sizing="sm" value={sort} onChange={(e) => setSort(e.target.value)}>
                            <option value="relevance">Relevance</option>
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

            {notFound && <p className="pt-4 ml-2 text-red-500 font-medium">No results found.</p>}
            {error && <p className="pt-4 ml-2 text-red-500 font-medium">{error}</p>}

            <div className={`${showList ? "block" : "hidden"} mt-4 relative z-10 bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden`}>
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
                                    <Link to={data.isbn ? `/edition/${encodeURIComponent(data.isbn)}` : "#"} className="group">
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

            {showList && !loading && (
                <PageNav offset={offset} limit={limit} hasMore={hasMore} resultCount={results.length} onPageChange={goToPage} />
            )}
        </div>
    );
}
