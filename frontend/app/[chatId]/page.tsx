"use client"

import Link from "next/link";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";

import Conversation from "@/components/Conversation";
import FormsPanel, { StatusFilter } from "@/components/FormsPanel";
import { RequestError, apiRequest, fetcher } from "@/utils/fetcher";
import { Chat, FormSubmission } from "@/utils/types";

type Notice = { kind: "error" | "info"; text: string };

export default function ChatPage({ params }: { params: { chatId: string } }) {
  const chatId = params.chatId;
  const { mutate: globalMutate } = useSWRConfig();

  const chat = useSWR<Chat, RequestError, { url: string }>({ url: `chat/${chatId}` }, fetcher);

  const [filter, setFilter] = useState<StatusFilter>("all");
  const forms = useSWR<FormSubmission[], RequestError, { url: string }>(
    { url: `chat/${chatId}/forms${filter === "all" ? "" : `?status=${filter}`}` },
    fetcher,
  );

  const [draft, setDraft] = useState("");
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const sending = pendingText !== null;

  // Re-read every cached forms view for this chat (all filters), not just the visible one.
  const refreshForms = () =>
    globalMutate((key: any) => typeof key?.url === "string" && key.url.startsWith(`chat/${chatId}/forms`));

  async function send() {
    const base = chat.data;
    const text = draft.trim();
    if (!base || sending || !text) return;

    setPendingText(text);
    setDraft("");
    setNotice(null);
    try {
      // The backend accepts the stored transcript + exactly one new user message.
      const updated = await apiRequest<Chat>(`chat/${chatId}`, {
        method: "PUT",
        body: JSON.stringify({ messages: [...base.messages, { role: "user", content: text }] }),
      });
      await chat.mutate(updated, { revalidate: false });
    } catch (err) {
      // The outcome can be uncertain (e.g. the connection dropped after the server saved).
      // Reload server state before offering a retry - never replay the request automatically.
      const fresh = await chat.mutate().catch(() => undefined);
      const processed =
        fresh && fresh.messages.length > base.messages.length && fresh.messages[base.messages.length]?.content === text;
      if (processed) {
        setNotice({ kind: "info", text: "The response was interrupted, but the server processed your message. Showing the saved result." });
      } else {
        setDraft(text); // keep the user's input so they can retry
        const message = err instanceof RequestError ? err.message : "Something went wrong.";
        setNotice({ kind: "error", text: `${message} Your message is still in the box below.` });
      }
    } finally {
      setPendingText(null);
      await refreshForms();
    }
  }

  if (chat.error instanceof RequestError && chat.error.status === 404) {
    return (
      <main className="mx-auto max-w-lg p-8 text-center">
        <h1 className="text-xl font-semibold">Chat not found</h1>
        <p className="mt-2 text-neutral-600">There is no chat with ID “{chatId}”.</p>
        <Link href="/" className="mt-4 inline-block text-blue-800 underline">
          Back to all chats
        </Link>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col lg:h-screen">
      <header className="flex items-center gap-4 border-b border-neutral-200 bg-white px-4 py-3">
        <Link href="/" className="text-sm text-blue-800 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">
          ← All chats
        </Link>
        <h1 className="truncate text-base font-semibold">
          Chat <span className="font-mono text-sm font-normal text-neutral-500">{chatId}</span>
        </h1>
      </header>

      <main className="grid flex-1 gap-4 p-4 lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_400px]">
        <section aria-label="Conversation" className="flex min-h-[60vh] flex-col rounded-lg border border-neutral-200 bg-white lg:min-h-0">
          <div className="flex flex-1 flex-col overflow-y-auto p-4">
            {chat.error ? (
              <div role="alert" className="m-auto text-sm text-red-800">
                Couldn’t load this chat{chat.error instanceof RequestError ? `: ${chat.error.message}` : "."}{" "}
                <button type="button" className="underline" onClick={() => chat.mutate()}>
                  Retry
                </button>
              </div>
            ) : !chat.data ? (
              <p className="m-auto text-sm text-neutral-500">Loading conversation…</p>
            ) : (
              <Conversation messages={chat.data.messages} pendingText={pendingText} />
            )}
          </div>

          <form
            className="border-t border-neutral-200 p-3"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            {notice && (
              <p role={notice.kind === "error" ? "alert" : "status"} className={`mb-2 text-sm ${notice.kind === "error" ? "text-red-800" : "text-neutral-700"}`}>
                {notice.text}
              </p>
            )}
            <div className="flex gap-2">
              <label htmlFor="message" className="sr-only">
                Message
              </label>
              <textarea
                id="message"
                rows={2}
                value={draft}
                disabled={sending}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder="Message the assistant (Enter to send, Shift+Enter for a new line)"
                className="flex-1 resize-none rounded-md border border-neutral-300 px-3 py-2 text-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-600/30 disabled:bg-neutral-50"
              />
              <button
                type="submit"
                disabled={sending || !chat.data || !draft.trim()}
                className="self-end rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {sending ? "Sending…" : "Send"}
              </button>
            </div>
          </form>
        </section>

        <FormsPanel
          filter={filter}
          onFilterChange={setFilter}
          forms={forms.data}
          error={forms.error}
          isLoading={forms.isLoading}
          onRefresh={refreshForms}
        />
      </main>
    </div>
  );
}
