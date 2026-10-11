import { FieldChange, ToolCall, ToolResult, statusLabel } from "@/utils/types";

const FIELD_LABELS: Record<string, string> = {
  name: "Name",
  email: "Email",
  phone_number: "Phone",
  status: "Status",
};

// Friendly text per error code; the raw server message stays in the collapsed details.
const ERROR_TEXT: Record<string, string> = {
  not_found: "That form doesn't exist in this chat.",
  ambiguous_target: "More than one form has that name, so the assistant needs to ask which one.",
  validation_error: "The details weren't valid.",
  write_failed: "The database write failed and was rolled back.",
  invalid_json: "The assistant sent a malformed request.",
  invalid_arguments: "The assistant sent a malformed request.",
  unknown_tool: "The assistant asked for an action that doesn't exist.",
};

function formatValue(field: string, value: unknown) {
  if (field === "status") return statusLabel(value as any);
  return value === null || value === undefined || value === "" ? "(empty)" : String(value);
}

function DeveloperDetails({ result, call }: { result: ToolResult; call?: ToolCall }) {
  return (
    <details className="mt-2 text-xs text-neutral-500">
      <summary className="cursor-pointer select-none rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">
        Developer details
      </summary>
      <div className="mt-1 space-y-1 font-mono break-all">
        <div>tool: {result.tool}</div>
        {call && <div>arguments: {call.function.arguments}</div>}
        {!result.ok && <div>error: {result.error.message}</div>}
      </div>
    </details>
  );
}

function ChangeList({ changes }: { changes: Record<string, FieldChange> }) {
  const entries = Object.entries(changes);
  if (!entries.length) return <p className="text-sm text-neutral-600">No fields changed. The values already matched.</p>;
  return (
    <dl className="mt-1 space-y-0.5 text-sm">
      {entries.map(([field, c]) => (
        <div key={field} className="flex flex-wrap gap-x-2">
          <dt className="font-medium text-neutral-700">{FIELD_LABELS[field] ?? field}:</dt>
          <dd>
            <span className="text-neutral-500 line-through decoration-neutral-400">{formatValue(field, c.from)}</span>
            <span aria-hidden="true"> → </span>
            <span className="sr-only"> changed to </span>
            <span className="font-medium text-neutral-900">{formatValue(field, c.to)}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * A receipt is rendered from the tool result the backend stored after the database
 * operation finished - not from anything the assistant wrote.
 */
export default function ActionReceipt({ result, call }: { result: ToolResult; call?: ToolCall }) {
  if (result.ok && result.action === "listed") {
    return (
      <p className="self-start text-xs text-neutral-500">
        Looked up {result.count} saved form{result.count === 1 ? "" : "s"}
      </p>
    );
  }

  if (!result.ok && result.error.code === "ambiguous_target") {
    return (
      <div role="status" className="w-full max-w-md self-start rounded-md border border-amber-300 border-l-4 border-l-amber-500 bg-amber-50 px-3 py-2">
        <p className="text-sm font-semibold text-amber-900">
          <span aria-hidden="true">? </span>Needs clarification
        </p>
        <p className="text-sm text-amber-950">{ERROR_TEXT.ambiguous_target} Nothing was changed.</p>
        <DeveloperDetails result={result} call={call} />
      </div>
    );
  }

  if (!result.ok) {
    return (
      <div role="status" className="w-full max-w-md self-start rounded-md border border-red-300 border-l-4 border-l-red-600 bg-red-50 px-3 py-2">
        <p className="text-sm font-semibold text-red-800">
          <span aria-hidden="true">✕ </span>Action failed
        </p>
        <p className="text-sm text-red-900">
          {ERROR_TEXT[result.error.code] ?? "The action could not be completed."} Nothing was changed by this action.
        </p>
        <DeveloperDetails result={result} call={call} />
      </div>
    );
  }

  const heading = { created: "Saved", updated: "Updated", deleted: "Deleted" }[result.action];
  const accent = result.action === "deleted" ? "border-l-neutral-500" : "border-l-emerald-600";
  return (
    <div role="status" className={`w-full max-w-md self-start rounded-md border border-neutral-200 border-l-4 ${accent} bg-white px-3 py-2 shadow-sm`}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-sm font-semibold text-neutral-900">
          <span aria-hidden="true">✓ </span>
          {heading}: {result.form.name}
        </p>
        <span className="text-[11px] uppercase tracking-wide text-neutral-400">App receipt</span>
      </div>
      {result.action === "updated" ? (
        <ChangeList changes={result.changes ?? {}} />
      ) : (
        <p className="text-sm text-neutral-600">
          {result.form.email} · {result.form.phone_number} · {statusLabel(result.form.status)}
        </p>
      )}
      <p className="mt-0.5 font-mono text-xs text-neutral-500">Form {result.form_id}</p>
      <DeveloperDetails result={result} call={call} />
    </div>
  );
}
