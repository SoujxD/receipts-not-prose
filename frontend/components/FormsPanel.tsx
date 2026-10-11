import { useState } from "react";

import { RequestError, apiRequest } from "@/utils/fetcher";
import { FormSubmission, STATUS_VALUES, Status, parseUtc, statusLabel } from "@/utils/types";

// "all" = no filter; otherwise the value sent as ?status= ("null" selects Unset).
export type StatusFilter = "all" | "null" | "1" | "2" | "3";

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  ...STATUS_VALUES.map((s) => ({ value: String(s) as StatusFilter, label: statusLabel(s) })),
];

const BADGE: Record<string, string> = {
  null: "border-neutral-300 bg-neutral-50 text-neutral-700",
  1: "border-sky-300 bg-sky-50 text-sky-900",
  2: "border-amber-300 bg-amber-50 text-amber-900",
  3: "border-emerald-300 bg-emerald-50 text-emerald-900",
};

function CopyId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() =>
        navigator.clipboard?.writeText(id).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          },
          () => undefined,
        )
      }
      className="rounded px-1 font-mono text-xs text-neutral-500 hover:bg-neutral-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600"
      aria-label={`Copy form ID ${id}`}
      title="Copy form ID"
    >
      {id} <span className="font-sans">{copied ? "· copied" : "· copy"}</span>
    </button>
  );
}

// OPTIONAL EXTRA (beyond the README): quick status change using the same PATCH endpoint.
function StatusSelect({ form, onSaved }: { form: FormSubmission; onSaved: () => Promise<unknown> }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function change(value: string) {
    const status: Status = value === "null" ? null : (Number(value) as Status);
    setSaving(true);
    setError(null);
    try {
      await apiRequest(`chat/${form.chat_id}/forms/${form.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
    } catch (err) {
      setError(err instanceof RequestError ? err.message : "Could not update status.");
    } finally {
      await onSaved(); // always re-read the saved state
      setSaving(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <label htmlFor={`status-${form.id}`} className="text-xs text-neutral-500">
        Set status
      </label>
      <select
        id={`status-${form.id}`}
        value={String(form.status)}
        disabled={saving}
        onChange={(e) => change(e.target.value)}
        className="rounded border border-neutral-300 bg-white px-1.5 py-0.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 disabled:opacity-60"
      >
        {STATUS_VALUES.map((s) => (
          <option key={String(s)} value={String(s)}>
            {statusLabel(s)}
          </option>
        ))}
      </select>
      {saving && <span className="text-xs text-neutral-500">Saving…</span>}
      {error && (
        <span role="alert" className="text-xs text-red-700">
          {error}
        </span>
      )}
    </div>
  );
}

function FormCard({ form, onChanged }: { form: FormSubmission; onChanged: () => Promise<unknown> }) {
  return (
    <li className="rounded-md border border-neutral-200 bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-medium text-neutral-900">{form.name}</h3>
        <span className={`shrink-0 rounded border px-1.5 py-0.5 text-xs font-medium ${BADGE[String(form.status)]}`}>
          {statusLabel(form.status)}
        </span>
      </div>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 text-sm">
        <dt className="text-neutral-500">Email</dt>
        <dd className="break-all">{form.email}</dd>
        <dt className="text-neutral-500">Phone</dt>
        <dd>{form.phone_number}</dd>
        <dt className="text-neutral-500">Saved</dt>
        <dd>{parseUtc(form.created_at).toLocaleString()}</dd>
      </dl>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <CopyId id={form.id} />
        <StatusSelect form={form} onSaved={onChanged} />
      </div>
    </li>
  );
}

export default function FormsPanel({
  filter,
  onFilterChange,
  forms,
  error,
  isLoading,
  onRefresh,
}: {
  filter: StatusFilter;
  onFilterChange: (f: StatusFilter) => void;
  forms: FormSubmission[] | undefined;
  error: unknown;
  isLoading: boolean;
  onRefresh: () => Promise<unknown>;
}) {
  const activeLabel = FILTERS.find((f) => f.value === filter)?.label;

  let body: React.ReactNode;
  if (error && !forms) {
    body = (
      <div role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
        Couldn’t load saved forms{error instanceof RequestError ? `: ${error.message}` : "."}{" "}
        <button type="button" onClick={() => onRefresh()} className="underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">
          Retry
        </button>
      </div>
    );
  } else if (isLoading && !forms) {
    body = <p className="text-sm text-neutral-500">Loading saved forms…</p>;
  } else if (!forms?.length) {
    body =
      filter === "all" ? (
        <p className="text-sm text-neutral-500">No forms saved in this chat yet. Ask the assistant to submit one.</p>
      ) : (
        <p className="text-sm text-neutral-500">
          No forms with status {activeLabel}.{" "}
          <button type="button" onClick={() => onFilterChange("all")} className="underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">
            Show all
          </button>
        </p>
      );
  } else {
    body = (
      <ul className="space-y-2">
        {forms.map((f) => (
          <FormCard key={f.id} form={f} onChanged={onRefresh} />
        ))}
      </ul>
    );
  }

  return (
    <section aria-labelledby="forms-heading" className="flex min-h-0 flex-col rounded-lg border border-neutral-200 bg-neutral-50">
      <div className="border-b border-neutral-200 p-4">
        <div className="flex items-baseline justify-between">
          <h2 id="forms-heading" className="font-semibold text-neutral-900">
            Saved interest forms
          </h2>
          {forms && (
            <span className="text-sm text-neutral-500">
              {forms.length} {filter === "all" ? "total" : "shown"}
            </span>
          )}
        </div>
        <p className="mt-0.5 text-xs text-neutral-500">Loaded from the database, refreshed after every action.</p>
        <div role="group" aria-label="Filter by status" className="mt-3 flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              aria-pressed={filter === f.value}
              onClick={() => onFilterChange(f.value)}
              className={`rounded-full border px-2.5 py-0.5 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
                filter === f.value
                  ? "border-slate-800 bg-slate-800 text-white"
                  : "border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-100"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        {filter !== "all" && (
          <p className="mt-2 text-xs text-neutral-600">
            Showing only {activeLabel}. Forms with other statuses are hidden, so a form you just changed may move out of
            this view.
          </p>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {Boolean(error) && forms && (
          <p role="alert" className="mb-2 text-xs text-red-800">
            Couldn’t refresh, so this is the last loaded data.{" "}
            <button type="button" onClick={() => onRefresh()} className="underline">
              Retry
            </button>
          </p>
        )}
        {body}
      </div>
    </section>
  );
}
