export type Status = 1 | 2 | 3 | null;

// null is "Unset" - a new form has no status yet. It is not the same as 1 (TO DO).
export const STATUS_LABELS: Record<string, string> = {
  null: "Unset",
  1: "TO DO",
  2: "IN PROGRESS",
  3: "COMPLETED",
};

export const statusLabel = (s: Status | undefined) => STATUS_LABELS[String(s ?? null)] ?? "Unknown";

export const STATUS_VALUES: Status[] = [null, 1, 2, 3];

export type FormSubmission = {
  id: string;
  chat_id: string;
  created_at: string;
  name: string;
  email: string;
  phone_number: string;
  status: Status;
  status_label: string;
};

export type ToolCall = {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
};

export type ChatMessage = {
  role: "user" | "assistant" | "tool" | "system";
  content: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  // Set on replies written by the application (not the model), e.g. when the model failed.
  app_generated?: boolean;
};

export type Chat = {
  id: string;
  created_at: string;
  messages: ChatMessage[];
};

export type FieldChange = { from: unknown; to: unknown };

// Shape of the JSON content of a tool message, written by the backend after the DB operation.
export type ToolResult =
  | {
      ok: true;
      tool: string;
      action: "created" | "updated" | "deleted";
      form_id: string;
      form: FormSubmission;
      changes?: Record<string, FieldChange>;
    }
  | { ok: true; tool: string; action: "listed"; count: number }
  | { ok: false; tool: string; error: { code: string; message: string } };

export function parseToolResult(content: string | null): ToolResult | null {
  try {
    const value = JSON.parse(content ?? "");
    return value && typeof value === "object" && "ok" in value ? (value as ToolResult) : null;
  } catch {
    return null; // e.g. legacy "Success" strings from the original starter
  }
}

// API timestamps are naive UTC.
export const parseUtc = (ts: string) => new Date(ts.endsWith("Z") ? ts : `${ts}Z`);
