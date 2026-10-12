export type SessionOut = {
  token: string;
  owner_id: string;
  is_guest: boolean;
  guest_ttl_hours: number;
};

export type MeOut = {
  owner_id: string;
  is_guest: boolean;
  email: string | null;
  display_name: string | null;
  title: string | null;
  company: string | null;
  guest_notice: string | null;
};

export type ProfileUpdate = {
  display_name?: string;
  title?: string;
  company?: string;
};

export type DocumentOut = {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  page_count: number | null;
  chunk_count: number;
  status: string;
  error: string | null;
};

export type SummaryOut = {
  text: string;
  cached: boolean;
  library_hash: string;
};

export type TranscribeOut = {
  text: string;
  model: string;
};

export type Citation = {
  filename: string;
  page: number | null;
  chunk_id: string;
  quote: string;
};

export type AnswerPayload = {
  text: string;
  citations: Citation[];
  refused: boolean;
  retrieved_chunk_ids?: string[];
  model?: string;
  latency_ms?: Record<string, unknown>;
};

export type AskOut = {
  thread_id: string;
  answer: AnswerPayload;
};

export type ChatMessageOut = {
  id: string;
  thread_id: string;
  role: string;
  content: string;
  citations_json: string | null;
  refused: boolean | null;
};

export type ThreadOut = {
  id: string;
  title: string;
  updated_at: string;
  document_ids: string[];
};

export type ClearOut = {
  documents_removed: number;
  chroma_remaining: number;
};
