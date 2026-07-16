import { useEffect, useState } from "react";
import { Modal, Button, Label, TextInput, Textarea, Checkbox, Radio, Alert, Spinner } from "flowbite-react";
import { suggestEdit } from "../api/client";
import { ENTITY_FIELD_CONFIG } from "../constants/entityFields";

function toDisplayValue(value, type) {
    if (value === undefined || value === null) return "";
    if (type === "json") return JSON.stringify(value);
    return String(value);
}

// entityType: "editions" | "works" | "authors"
export default function SuggestEditModal({ open, onClose, entityType, identifier, record }) {
    const config = ENTITY_FIELD_CONFIG[entityType];
    const [action, setAction] = useState("patch");
    const [selected, setSelected] = useState({});
    const [values, setValues] = useState({});
    const [note, setNote] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [result, setResult] = useState(null); // { ok, message }

    useEffect(() => {
        if (!open) return;
        setAction("patch");
        setNote("");
        setResult(null);
        const initialValues = {};
        config.fields.forEach((f) => {
            initialValues[f.name] = toDisplayValue(record?.[f.name], f.type);
        });
        setValues(initialValues);
        setSelected({});
    }, [open, record, config]);

    if (!config) return null;

    const toggleField = (name) => {
        setSelected((s) => ({ ...s, [name]: !s[name] }));
    };

    const handleSubmit = async () => {
        setResult(null);

        if (action === "patch") {
            const chosenFields = config.fields.filter((f) => selected[f.name]);
            if (chosenFields.length === 0) {
                setResult({ ok: false, message: "Select at least one field to change." });
                return;
            }

            const patch = {};
            for (const f of chosenFields) {
                const raw = values[f.name];
                if (f.type === "json") {
                    try {
                        patch[f.name] = raw.trim() === "" ? [] : JSON.parse(raw);
                    } catch {
                        setResult({ ok: false, message: `"${f.label}" must be valid JSON (e.g. ["a", "b"]).` });
                        return;
                    }
                } else if (f.type === "number") {
                    patch[f.name] = raw === "" ? null : Number(raw);
                } else {
                    patch[f.name] = raw;
                }
            }

            setSubmitting(true);
            try {
                const data = await suggestEdit(config.route, identifier, { action: "patch", patch, note });
                setResult({ ok: true, message: `Suggestion #${data.id} submitted (status: ${data.status}).` });
            } catch (err) {
                setResult({ ok: false, message: err.response?.data?.error || err.response?.data?.message || "Failed to submit suggestion." });
            } finally {
                setSubmitting(false);
            }
        } else {
            setSubmitting(true);
            try {
                const data = await suggestEdit(config.route, identifier, { action: "delete", note });
                setResult({ ok: true, message: `Suggestion #${data.id} submitted (status: ${data.status}).` });
            } catch (err) {
                setResult({ ok: false, message: err.response?.data?.error || err.response?.data?.message || "Failed to submit suggestion." });
            } finally {
                setSubmitting(false);
            }
        }
    };

    return (
        <Modal show={open} onClose={onClose} size="xl">
            <Modal.Header>Suggest an edit &mdash; {config.label} {identifier}</Modal.Header>
            <Modal.Body>
                <div className="flex flex-col gap-4">
                    <p className="text-sm text-gray-500">
                        Suggestions are reviewed by an operator before they affect what the API serves. No login required.
                    </p>

                    <div className="flex gap-6">
                        <div className="flex items-center gap-2">
                            <Radio id="action-patch" name="action" checked={action === "patch"} onChange={() => setAction("patch")} />
                            <Label htmlFor="action-patch">Correct field(s)</Label>
                        </div>
                        <div className="flex items-center gap-2">
                            <Radio id="action-delete" name="action" checked={action === "delete"} onChange={() => setAction("delete")} />
                            <Label htmlFor="action-delete">Revert to upstream OpenLibrary data</Label>
                        </div>
                    </div>

                    {action === "patch" && (
                        <div className="flex flex-col gap-3 max-h-96 overflow-y-auto pr-1">
                            {config.fields.map((f) => (
                                <div key={f.name} className="flex flex-col gap-1 border-b border-gray-100 pb-2">
                                    <div className="flex items-center gap-2">
                                        <Checkbox
                                            id={`field-${f.name}`}
                                            checked={!!selected[f.name]}
                                            onChange={() => toggleField(f.name)}
                                        />
                                        <Label htmlFor={`field-${f.name}`}>{f.label}</Label>
                                        {f.type === "json" && <span className="text-xs text-gray-400">(JSON array)</span>}
                                    </div>
                                    {selected[f.name] && f.type === "textarea" && (
                                        <Textarea
                                            rows={3}
                                            value={values[f.name] ?? ""}
                                            onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                                        />
                                    )}
                                    {selected[f.name] && f.type !== "textarea" && (
                                        <TextInput
                                            type={f.type === "number" ? "number" : "text"}
                                            value={values[f.name] ?? ""}
                                            onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))}
                                        />
                                    )}
                                </div>
                            ))}
                        </div>
                    )}

                    <div>
                        <Label htmlFor="note">Note (optional)</Label>
                        <Textarea id="note" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why is this change needed?" />
                    </div>

                    {result && (
                        <Alert color={result.ok ? "success" : "failure"}>{result.message}</Alert>
                    )}
                </div>
            </Modal.Body>
            <Modal.Footer>
                <Button onClick={handleSubmit} disabled={submitting}>
                    {submitting ? <Spinner size="sm" light /> : "Submit suggestion"}
                </Button>
                <Button color="gray" onClick={onClose}>
                    Close
                </Button>
            </Modal.Footer>
        </Modal>
    );
}
