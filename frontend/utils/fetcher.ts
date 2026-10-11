export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class RequestError extends Error {
  status: number;
  info: unknown;

  constructor(status: number, message: string, info?: unknown) {
    super(message);
    this.status = status;
    this.info = info;
  }
}

// FastAPI returns {"detail": "..."} or, for validation errors, {"detail": [{msg, loc}, ...]}.
function describeDetail(body: any, fallback: string): string {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: any) => d?.msg ?? String(d)).join("; ");
  }
  return fallback;
}

export async function apiRequest<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${API_URL}/${path}`, {
      ...init,
      headers: { Accept: "application/json", "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new RequestError(0, `Could not reach the server at ${API_URL}. Is the backend running?`);
  }

  if (!r.ok) {
    const body = await r.json().catch(() => undefined);
    throw new RequestError(r.status, describeDetail(body, `Request failed (${r.status})`), body);
  }

  // 204 No Content (e.g. DELETE) has no JSON body to parse.
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

// Response types are declared at each useSWR<T> call site.
export async function fetcher(args: { url: string }): Promise<any> {
  return apiRequest(args.url);
}
