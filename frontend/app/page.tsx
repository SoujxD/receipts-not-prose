"use client"

import { RequestError, apiRequest, fetcher } from "@/utils/fetcher";
import { Chat, parseUtc } from "@/utils/types";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";

export default function Home() {
  const router = useRouter()
  const { data, error, mutate } = useSWR<Chat[], RequestError, { url: string }>({ url: `chat` }, fetcher) // make GET request
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  async function createChat() { // make POST request
    setCreating(true)
    setCreateError(null)
    try {
      const json = await apiRequest<Chat>("chat", { method: "POST", body: JSON.stringify({}) })
      router.push(`/${json.id}`)
    } catch (err) {
      setCreateError(err instanceof RequestError ? err.message : "Could not create a chat.")
      setCreating(false)
    }
  }

  return <main className="mx-auto max-w-3xl p-4 sm:p-8">
    <div className="flex justify-between items-center mb-4 gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Chats</h1>
        <p className="text-sm text-neutral-600">Talk to the assistant to submit, update or delete interest forms.</p>
      </div>
      <button
        className="shrink-0 rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2 disabled:opacity-50"
        onClick={() => createChat()}
        disabled={creating}
      >
        {creating ? "Creating…" : "Create Chat"}
      </button>
    </div>
    {createError && <p role="alert" className="mb-3 text-sm text-red-800">{createError}</p>}
    <div className="border rounded-lg border-neutral-200 bg-white shadow-sm">
      {error ? (
        <p role="alert" className="p-4 text-sm text-red-800">
          Couldn’t load chats{error instanceof RequestError ? `: ${error.message}` : "."}{" "}
          <button type="button" className="underline" onClick={() => mutate()}>Retry</button>
        </p>
      ) : !data ? (
        <p className="p-4 text-sm text-neutral-500">Loading chats…</p>
      ) : !data.length ? (
        <p className="p-4 text-sm text-neutral-500">No chats yet. Create one to get started.</p>
      ) : (
        <table className="w-full text-sm text-left">
          <caption className="sr-only">10 most recent chats</caption>
          <thead className="text-xs uppercase text-neutral-500">
            <tr>
              <th scope="col" className="font-semibold px-4 py-3">ID</th>
              <th scope="col" className="font-semibold px-4 py-3">Created At</th>
            </tr>
          </thead>
          <tbody>
            {data.map((s) => (
              <tr key={s.id} className="border-t hover:bg-neutral-50">
                <td className="px-4 py-3 font-mono">
                  <Link href={`/${s.id}`} className="text-blue-800 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">
                    {s.id}
                  </Link>
                </td>
                <td className="px-4 py-3">{parseUtc(s.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  </main>
}
