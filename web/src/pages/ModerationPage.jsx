import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { TextInput, Select, Label, Button, Table, Badge, Spinner, Alert } from "flowbite-react";
import { listSuggestions, approveSuggestion, rejectSuggestion } from "../api/client";

const TOKEN_STORAGE_KEY = "ol_edit_token";

const STATUS_COLORS = { pending: "warning", approved: "success", rejected: "failure" };

export default function ModerationPage() {
    const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_STORAGE_KEY) || "");
    const [status, setStatus] = useState("pending");
    const [entityType, setEntityType] = useState("");
    const [suggestions, setSuggestions] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [actionError, setActionError] = useState(null);

    const fetchSuggestions = () => {
        if (!token) return;
        setLoading(true);
        setError(null);
        listSuggestions(token, { status: status || undefined, entity_type: entityType || undefined }).then(
            (data) => {
                setSuggestions(data.suggestions);
                setLoading(false);
                sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
            },
            (err) => {
                setLoading(false);
                setSuggestions(null);
                setError(err.response?.status === 404 ? "Invalid edit token, or moderation is not enabled on this API." : "Failed to load suggestions.");
            }
        );
    };

    useEffect(() => {
        if (token) fetchSuggestions();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const handleApprove = (id) => {
        setActionError(null);
        approveSuggestion(token, id).then(fetchSuggestions, (err) => {
            setActionError(err.response?.data?.message || "Failed to approve suggestion.");
        });
    };

    const handleReject = (id) => {
        setActionError(null);
        rejectSuggestion(token, id).then(fetchSuggestions, (err) => {
            setActionError(err.response?.data?.message || "Failed to reject suggestion.");
        });
    };

    return (
        <div>
            <Link to="/" className="text-sm text-blue-600 hover:underline">&larr; Back to search</Link>
            <h1 className="text-xl font-bold pt-2 pb-4">Suggestion moderation</h1>

            <div className="flex flex-col gap-3 bg-gray-50 p-4 rounded-lg border border-gray-200">
                <div>
                    <Label htmlFor="token" value="Edit token" />
                    <TextInput
                        id="token"
                        type="password"
                        placeholder="X-Edit-Token"
                        value={token}
                        onChange={(e) => setToken(e.target.value)}
                    />
                </div>

                <div className="flex flex-wrap gap-4 items-end">
                    <div>
                        <Label htmlFor="status" value="Status" className="text-xs text-gray-500" />
                        <Select id="status" sizing="sm" value={status} onChange={(e) => setStatus(e.target.value)}>
                            <option value="">All</option>
                            <option value="pending">Pending</option>
                            <option value="approved">Approved</option>
                            <option value="rejected">Rejected</option>
                        </Select>
                    </div>
                    <div>
                        <Label htmlFor="entity_type" value="Entity type" className="text-xs text-gray-500" />
                        <Select id="entity_type" sizing="sm" value={entityType} onChange={(e) => setEntityType(e.target.value)}>
                            <option value="">All</option>
                            <option value="editions">Editions</option>
                            <option value="works">Works</option>
                            <option value="authors">Authors</option>
                        </Select>
                    </div>
                    <Button size="sm" onClick={fetchSuggestions} disabled={!token}>
                        Load suggestions
                    </Button>
                </div>
            </div>

            {error && <Alert color="failure" className="mt-4">{error}</Alert>}
            {actionError && <Alert color="failure" className="mt-4">{actionError}</Alert>}

            {loading && (
                <div className="flex justify-center py-16">
                    <Spinner size="xl" />
                </div>
            )}

            {!loading && suggestions && (
                suggestions.length === 0 ? (
                    <p className="mt-6 text-gray-500">No suggestions match these filters.</p>
                ) : (
                    <div className="mt-6 overflow-x-auto">
                        <Table>
                            <Table.Head>
                                <Table.HeadCell>ID</Table.HeadCell>
                                <Table.HeadCell>Entity</Table.HeadCell>
                                <Table.HeadCell>Action</Table.HeadCell>
                                <Table.HeadCell>Patch</Table.HeadCell>
                                <Table.HeadCell>Note</Table.HeadCell>
                                <Table.HeadCell>Status</Table.HeadCell>
                                <Table.HeadCell>&nbsp;</Table.HeadCell>
                            </Table.Head>
                            <Table.Body className="divide-y">
                                {suggestions.map((s) => (
                                    <Table.Row key={s.id} className="bg-white align-top">
                                        <Table.Cell>{s.id}</Table.Cell>
                                        <Table.Cell>
                                            <div className="text-sm">{s.entity_type}</div>
                                            <div className="text-xs text-gray-400">{s.ol_id}</div>
                                        </Table.Cell>
                                        <Table.Cell>{s.action}</Table.Cell>
                                        <Table.Cell className="max-w-xs">
                                            <pre className="text-xs whitespace-pre-wrap break-words">{JSON.stringify(s.patch, null, 2)}</pre>
                                        </Table.Cell>
                                        <Table.Cell className="max-w-xs text-xs text-gray-600">{s.note}</Table.Cell>
                                        <Table.Cell>
                                            <Badge color={STATUS_COLORS[s.status] || "gray"}>{s.status}</Badge>
                                        </Table.Cell>
                                        <Table.Cell>
                                            {s.status === "pending" && (
                                                <div className="flex flex-col gap-1">
                                                    <Button size="xs" color="success" onClick={() => handleApprove(s.id)}>
                                                        Approve
                                                    </Button>
                                                    <Button size="xs" color="failure" onClick={() => handleReject(s.id)}>
                                                        Reject
                                                    </Button>
                                                </div>
                                            )}
                                        </Table.Cell>
                                    </Table.Row>
                                ))}
                            </Table.Body>
                        </Table>
                    </div>
                )
            )}
        </div>
    );
}
