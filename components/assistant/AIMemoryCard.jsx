/**
 * AIMemoryCard
 * ============
 * Lets the user audit, edit, and delete the durable facts Nouri remembers
 * about them across sessions. Shown inside the user Settings page.
 *
 * - Lists every memory (key, value, source, confidence, last seen)
 * - Inline-edit / add a new fact
 * - Delete a single fact, or forget everything in one tap
 *
 * Designed to feel safe and reversible: every destructive action requires
 * an explicit confirmation, and any error from the backend is surfaced
 * with both a human message and the request-id chip for support triage.
 */

import React from "react";
import Card from "../common/Card";
import Button from "../common/Button";
import Input from "../common/Input";
import aiChatService from "../../utils/services/aiChatService";

const SOURCE_LABELS = {
  explicit: { label: "You told me", color: "bg-emerald-100 text-emerald-700" },
  extracted: { label: "I noticed", color: "bg-sky-100 text-sky-700" },
  profile: { label: "From profile", color: "bg-amber-100 text-amber-700" },
  system: { label: "System", color: "bg-gray-100 text-gray-700" },
};

function prettyKey(key) {
  if (!key) return "";
  return String(key).replace(/_/g, " ");
}

function formatTimestamp(value) {
  if (!value) return "";
  try {
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default function AIMemoryCard({ userId }) {
  const [memories, setMemories] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [requestId, setRequestId] = React.useState(null);
  const [confirmClearAll, setConfirmClearAll] = React.useState(false);
  const [confirmDeleteKey, setConfirmDeleteKey] = React.useState(null);
  const [newKey, setNewKey] = React.useState("");
  const [newValue, setNewValue] = React.useState("");
  const [savingNew, setSavingNew] = React.useState(false);
  const [savedHint, setSavedHint] = React.useState("");

  const load = React.useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    setRequestId(null);
    try {
      const data = await aiChatService.listMemories(userId);
      setMemories(Array.isArray(data?.memories) ? data.memories : []);
    } catch (err) {
      setError(err?.aiError?.message || err?.message || "Could not load memories.");
      setRequestId(err?.aiError?.requestId || err?.requestId || null);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  React.useEffect(() => {
    load();
  }, [load]);

  const handleAdd = async (e) => {
    e?.preventDefault?.();
    if (!newKey.trim() || !newValue.trim()) return;
    setSavingNew(true);
    setError(null);
    try {
      await aiChatService.upsertMemory(userId, {
        key: newKey.trim(),
        value: newValue.trim(),
        confidence: 1,
        source: "explicit",
      });
      setNewKey("");
      setNewValue("");
      setSavedHint("Saved.");
      window.setTimeout(() => setSavedHint(""), 2000);
      await load();
    } catch (err) {
      setError(err?.aiError?.message || err?.message || "Could not save memory.");
      setRequestId(err?.aiError?.requestId || err?.requestId || null);
    } finally {
      setSavingNew(false);
    }
  };

  const handleDelete = async (key) => {
    if (!key) return;
    setError(null);
    try {
      await aiChatService.deleteMemory(userId, key);
      setConfirmDeleteKey(null);
      await load();
    } catch (err) {
      setError(err?.aiError?.message || err?.message || "Could not delete memory.");
      setRequestId(err?.aiError?.requestId || err?.requestId || null);
    }
  };

  const handleClearAll = async () => {
    setError(null);
    try {
      await aiChatService.clearAllMemories(userId);
      setConfirmClearAll(false);
      await load();
    } catch (err) {
      setError(err?.aiError?.message || err?.message || "Could not clear memories.");
      setRequestId(err?.aiError?.requestId || err?.requestId || null);
    }
  };

  return (
    <Card>
      <div className="p-6">
        <div className="flex items-start justify-between mb-4 gap-4 flex-wrap">
          <div>
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <span role="img" aria-hidden="true">🧠</span>
              What Nouri Remembers About You
            </h2>
            <p className="text-sm text-gray-600 mt-1 max-w-2xl">
              Nouri saves a few stable facts (household size, dietary needs,
              schedule) so you don&apos;t have to repeat yourself. You stay in
              control — view, edit, or wipe anything at any time.
            </p>
          </div>
          {memories.length > 0 && !confirmClearAll && (
            <Button
              variant="secondary"
              onClick={() => setConfirmClearAll(true)}
              aria-label="Forget everything Nouri remembers about me"
            >
              <i className="fas fa-eraser mr-2" aria-hidden="true" />
              Forget all
            </Button>
          )}
        </div>

        {confirmClearAll && (
          <div className="mb-4 p-4 rounded-lg border border-red-200 bg-red-50 text-sm text-red-800 flex items-center justify-between flex-wrap gap-3">
            <span>This will permanently delete every memory Nouri has of you.</span>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setConfirmClearAll(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={handleClearAll} className="!bg-red-600 hover:!bg-red-700">
                Yes, forget everything
              </Button>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 p-3 rounded-lg border border-amber-200 bg-amber-50 text-sm text-amber-800">
            <div>{error}</div>
            {requestId && (
              <div className="text-xs mt-1 font-mono opacity-75">request id: {requestId}</div>
            )}
          </div>
        )}

        {loading ? (
          <div className="py-8 text-center text-gray-500 text-sm">
            <i className="fas fa-spinner fa-spin mr-2" aria-hidden="true" />
            Loading saved memories…
          </div>
        ) : memories.length === 0 ? (
          <div className="py-6 text-center text-gray-500 text-sm border border-dashed border-gray-300 rounded-lg">
            Nothing saved yet. As you chat with Nouri, stable facts (like
            household size or dietary needs) will appear here.
          </div>
        ) : (
          <ul className="divide-y divide-gray-100 border border-gray-100 rounded-lg overflow-hidden">
            {memories.map((m) => {
              const source = SOURCE_LABELS[m.source] || SOURCE_LABELS.system;
              const isConfirming = confirmDeleteKey === m.key;
              return (
                <li key={m.id || m.key} className="p-3 sm:p-4 hover:bg-gray-50">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-gray-900 capitalize">
                          {prettyKey(m.key)}
                        </span>
                        <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${source.color}`}>
                          {source.label}
                        </span>
                        {typeof m.confidence === "number" && m.confidence < 0.7 && (
                          <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                            unsure
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-700 mt-1 break-words">{m.value}</p>
                      {m.last_seen && (
                        <p className="text-[11px] text-gray-400 mt-1">
                          last seen {formatTimestamp(m.last_seen)}
                        </p>
                      )}
                    </div>
                    {isConfirming ? (
                      <div className="flex gap-2 shrink-0">
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteKey(null)}
                          className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-700 hover:bg-gray-100"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(m.key)}
                          className="text-xs px-2 py-1 rounded bg-red-600 text-white hover:bg-red-700"
                        >
                          Confirm
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteKey(m.key)}
                        className="text-xs text-gray-400 hover:text-red-600 transition shrink-0"
                        aria-label={`Forget ${prettyKey(m.key)}`}
                      >
                        <i className="fas fa-times" aria-hidden="true" /> Forget
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <form onSubmit={handleAdd} className="mt-6 border-t border-gray-100 pt-4">
          <h3 className="text-sm font-semibold text-gray-800 mb-2">
            Teach Nouri something new
          </h3>
          <div className="flex gap-2 flex-wrap items-end">
            <div className="flex-1 min-w-[140px]">
              <Input
                label="Key"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="e.g. household_size"
                aria-label="Memory key"
                disabled={savingNew}
              />
            </div>
            <div className="flex-[2] min-w-[200px]">
              <Input
                label="Value"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="e.g. 4 people, including 2 kids"
                aria-label="Memory value"
                disabled={savingNew}
              />
            </div>
            <Button
              type="submit"
              variant="primary"
              disabled={savingNew || !newKey.trim() || !newValue.trim()}
            >
              {savingNew ? "Saving…" : "Save"}
            </Button>
          </div>
          {savedHint && (
            <p className="text-xs text-emerald-700 mt-2" role="status">
              {savedHint}
            </p>
          )}
          <p className="text-xs text-gray-500 mt-2">
            Tip: keys should be short and lowercase (use{" "}
            <code className="px-1 bg-gray-100 rounded">snake_case</code>). Existing
            facts with the same key are overwritten.
          </p>
        </form>
      </div>
    </Card>
  );
}
