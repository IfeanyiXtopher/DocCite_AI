import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { ApiError, api } from "../api/client";
import type { DocumentOut } from "../api/types";

type Props = {
  busy: boolean;
  disabled: boolean;
  uploadBusy: boolean;
  threadDocs: DocumentOut[];
  onAsk: (question: string) => Promise<void>;
  onUpload: (files: FileList) => Promise<void>;
  onDetach: (docId: string) => Promise<void>;
};

const ACCEPT = ".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown";

/** Library rows set this MIME; plain text alone is not a doc id (avoids drag-selected questions). */
const DOC_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function lookslikeDocId(value: string): boolean {
  return DOC_ID_RE.test(value.trim());
}

function readDroppedDocId(dt: DataTransfer): string | null {
  const custom = dt.getData("application/x-doccite-doc")?.trim();
  if (custom && lookslikeDocId(custom)) return custom;
  const plain = dt.getData("text/plain")?.trim();
  if (plain && lookslikeDocId(plain)) return plain;
  return null;
}

function pickRecorderMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t));
}

function extensionForMime(mime: string): string {
  if (mime.includes("mp4")) return "mp4";
  if (mime.includes("ogg")) return "ogg";
  return "webm";
}

export function Composer({
  busy,
  disabled,
  uploadBusy,
  threadDocs,
  onAsk,
  onUpload,
  onDetach,
}: Props) {
  const [question, setQuestion] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    return () => {
      mediaRef.current?.stop();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  async function submit(text?: string) {
    const q = (text ?? question).trim();
    if (!q || disabled || busy || transcribing) return;
    setQuestion("");
    await onAsk(q);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    await submit();
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  }

  async function handleFiles() {
    const files = fileRef.current?.files;
    if (!files?.length) return;
    await onUpload(files);
    if (fileRef.current) fileRef.current.value = "";
  }

  function stopTracks() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  async function finishRecording(blob: Blob, mime: string) {
    setTranscribing(true);
    setVoiceError(null);
    try {
      const ext = extensionForMime(mime);
      const result = await api.transcribe(blob, `recording.${ext}`);
      const text = result.text.trim();
      if (!text) {
        setVoiceError("No speech detected. Try again.");
        return;
      }
      setQuestion(text);
      if (!disabled && !busy) {
        await submit(text);
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Transcription failed";
      setVoiceError(msg);
    } finally {
      setTranscribing(false);
    }
  }

  async function toggleVoice() {
    if (transcribing || busy) return;
    setVoiceError(null);

    if (recording && mediaRef.current) {
      mediaRef.current.stop();
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceError("Voice input is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = pickRecorderMime();
      const recorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      mediaRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        setRecording(false);
        mediaRef.current = null;
        const usedMime = recorder.mimeType || mime || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: usedMime });
        chunksRef.current = [];
        stopTracks();
        if (blob.size < 200) {
          setVoiceError("Recording too short. Hold a bit longer.");
          return;
        }
        void finishRecording(blob, usedMime);
      };
      recorder.onerror = () => {
        setRecording(false);
        mediaRef.current = null;
        stopTracks();
        setVoiceError("Recording failed.");
      };

      recorder.start();
      setRecording(true);
    } catch {
      stopTracks();
      setVoiceError("Microphone permission denied or unavailable.");
    }
  }

  const voiceBusy = recording || transcribing;

  return (
    <div className="composer-wrap">
      {threadDocs.length ? (
        <div className="thread-docs">
          {threadDocs.map((d) => (
            <span
              key={d.id}
              className={`thread-doc-chip status-${d.status}`}
              title={d.filename}
            >
              <span className="chip-name">{d.filename}</span>
              <button
                type="button"
                className="chip-remove"
                aria-label={`Remove ${d.filename} from chat`}
                onClick={() => void onDetach(d.id)}
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="attach-hint">
          Upload, click a Library file, or drag it into this chat area to start
          asking.
        </p>
      )}

      {voiceError ? <p className="voice-error">{voiceError}</p> : null}

      <form className="composer" onSubmit={(e) => void handleSubmit(e)}>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          disabled={uploadBusy || voiceBusy}
          onChange={() => void handleFiles()}
        />
        <button
          type="button"
          className="composer-icon"
          title="Upload documents to this chat"
          aria-label="Upload documents to this chat"
          disabled={uploadBusy || voiceBusy}
          onClick={() => fileRef.current?.click()}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M12 5v14M5 12h14"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </svg>
        </button>
        <textarea
          rows={1}
          placeholder={
            recording
              ? "Listening… click the mic to stop"
              : transcribing
                ? "DocCite is transcribing…"
                : disabled
                  ? "Attach a document to this chat first…"
                  : "Ask DocCite about the documents in this chat…"
          }
          value={question}
          disabled={disabled || busy || voiceBusy}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button
          type="button"
          className={`composer-icon mic-btn${recording ? " recording" : ""}`}
          title={
            recording
              ? "Stop and transcribe"
              : "Speak a question"
          }
          aria-label={recording ? "Stop recording" : "Start voice input"}
          aria-pressed={recording}
          disabled={busy || transcribing}
          onClick={() => void toggleVoice()}
        >
          {transcribing ? (
            <span className="mic-spinner" aria-hidden="true" />
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M12 14a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v4a3 3 0 0 0 3 3Z"
                stroke="currentColor"
                strokeWidth="1.8"
              />
              <path
                d="M5 11a7 7 0 0 0 14 0M12 18v3"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          )}
        </button>
        <button
          type="submit"
          className="composer-send"
          disabled={disabled || busy || voiceBusy || !question.trim()}
          aria-label="Send"
          title="Send"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M5 12h14M13 6l6 6-6 6"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </form>
    </div>
  );
}

export { readDroppedDocId, lookslikeDocId };
