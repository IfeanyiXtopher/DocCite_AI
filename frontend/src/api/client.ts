import type {
  AskOut,
  ChatMessageOut,
  ClearOut,
  DocumentOut,
  MeOut,
  ProfileUpdate,
  SessionOut,
  SummaryOut,
  ThreadOut,
  TranscribeOut,
} from "./types";

const TOKEN_KEY = "doccite_session_token";

export function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (raw && raw.trim()) {
    return raw.replace(/\/$/, "");
  }
  // Local Vite default — FastAPI (often :8001 if :8000 is taken)
  return "http://127.0.0.1:8001";
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => JSON.stringify(d)).join("; ");
    }
  } catch {
    /* ignore */
  }
  return res.statusText || `HTTP ${res.status}`;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  auth = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (auth) {
    const token = getToken();
    if (token) {
      headers.set("X-DocCite-Session", token);
    }
  }
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${getApiBase()}${path}`, { ...init, headers });
  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res));
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/health", {}, false),

  guest: () =>
    request<SessionOut>("/auth/guest", { method: "POST" }, false),

  register: (email: string, password: string) =>
    request<SessionOut>(
      "/auth/register",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false,
    ),

  login: (email: string, password: string) =>
    request<SessionOut>(
      "/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      false,
    ),

  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),

  me: () => request<MeOut>("/me"),

  updateProfile: (body: ProfileUpdate) =>
    request<MeOut>("/me/profile", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  documents: () => request<DocumentOut[]>("/documents"),

  deleteDocument: (docId: string) =>
    request<{ status: string; id: string }>(`/documents/${docId}`, {
      method: "DELETE",
    }),

  upload: (file: File, threadId?: string | null) => {
    const body = new FormData();
    body.append("file", file);
    if (threadId) body.append("thread_id", threadId);
    return request<DocumentOut>("/documents/upload", { method: "POST", body });
  },

  summary: (force = false) =>
    request<SummaryOut>(`/summary?force=${force ? "true" : "false"}`),

  documentSummary: (docId: string, force = false) =>
    request<SummaryOut>(
      `/documents/${encodeURIComponent(docId)}/summary?force=${force ? "true" : "false"}`,
    ),

  transcribe: (audio: Blob, filename = "recording.webm") => {
    const body = new FormData();
    body.append("file", audio, filename);
    return request<TranscribeOut>("/transcribe", { method: "POST", body });
  },

  ask: (question: string, threadId: string) =>
    request<AskOut>("/ask", {
      method: "POST",
      body: JSON.stringify({
        question,
        thread_id: threadId,
      }),
    }),

  createThread: () =>
    request<ThreadOut>("/chats/threads", { method: "POST" }),

  deleteThread: (threadId: string) =>
    request<{ status: string; id: string }>(`/chats/threads/${threadId}`, {
      method: "DELETE",
    }),

  threads: (limit = 40) =>
    request<ThreadOut[]>(`/chats/threads?limit=${limit}`),

  threadDocuments: (threadId: string) =>
    request<DocumentOut[]>(`/chats/threads/${threadId}/documents`),

  attachDocuments: (threadId: string, docIds: string[]) =>
    request<DocumentOut[]>(`/chats/threads/${threadId}/documents`, {
      method: "POST",
      body: JSON.stringify({ doc_ids: docIds }),
    }),

  detachDocument: (threadId: string, docId: string) =>
    request<{ status: string }>(
      `/chats/threads/${threadId}/documents/${docId}`,
      { method: "DELETE" },
    ),

  messages: (limit = 50, threadId?: string | null) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (threadId) q.set("thread_id", threadId);
    return request<ChatMessageOut[]>(`/chats/messages?${q.toString()}`);
  },

  clearLibrary: () =>
    request<ClearOut>("/library", { method: "DELETE" }),
};

export { ApiError };
