import { useEffect, useMemo, useRef } from "react";

import ActionReceipt from "@/components/ActionReceipt";
import { ChatMessage, ToolCall, parseToolResult } from "@/utils/types";

export default function Conversation({
  messages,
  pendingText,
}: {
  messages: ChatMessage[];
  pendingText: string | null;
}) {
  const endRef = useRef<HTMLLIElement>(null);

  // tool_call_id -> the assistant's call, so receipts can show the raw call in developer details.
  const callsById = useMemo(() => {
    const map = new Map<string, ToolCall>();
    messages.forEach((m) => m.tool_calls?.forEach((c) => map.set(c.id, c)));
    return map;
  }, [messages]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, pendingText]);

  if (!messages.length && !pendingText) {
    return (
      <div className="m-auto max-w-sm text-center text-sm text-neutral-500">
        <p className="font-medium text-neutral-700">Start the conversation</p>
        <p className="mt-1">
          Try “I’d like to submit an interest form”. Saved, updated and deleted forms appear as receipts here and in
          the panel.
        </p>
      </div>
    );
  }

  return (
    <ol className="flex flex-col gap-3" aria-label="Messages">
      {messages.map((m, i) => {
        const key = m.tool_call_id ?? `${m.role}-${i}`;
        if (m.role === "user") {
          return (
            <li key={key} className="max-w-[80%] self-end whitespace-pre-wrap rounded-lg bg-slate-800 px-3 py-2 text-sm text-white">
              <span className="sr-only">You: </span>
              {m.content}
            </li>
          );
        }
        if (m.role === "assistant") {
          if (!m.content) return null; // tool-call-only turn: the receipts below say what happened
          if (m.app_generated) {
            return (
              <li key={key} className="max-w-[85%] self-start rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950">
                <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">Application notice</p>
                <p className="whitespace-pre-wrap">{m.content}</p>
              </li>
            );
          }
          return (
            <li key={key} className="max-w-[80%] self-start whitespace-pre-wrap rounded-lg border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm text-neutral-900">
              <span className="sr-only">Assistant: </span>
              {m.content}
            </li>
          );
        }
        if (m.role === "tool") {
          const result = parseToolResult(m.content);
          return (
            <li key={key} className="flex flex-col">
              {result ? (
                <ActionReceipt result={result} call={m.tool_call_id ? callsById.get(m.tool_call_id) : undefined} />
              ) : (
                <p className="self-start text-xs text-neutral-500">Legacy tool response: {m.content}</p>
              )}
            </li>
          );
        }
        return null;
      })}
      {pendingText && (
        <>
          <li className="max-w-[80%] self-end whitespace-pre-wrap rounded-lg bg-slate-800/70 px-3 py-2 text-sm text-white">
            {pendingText}
          </li>
          <li className="self-start text-sm text-neutral-500" role="status">
            Assistant is working…
          </li>
        </>
      )}
      <li ref={endRef} aria-hidden="true" />
    </ol>
  );
}
