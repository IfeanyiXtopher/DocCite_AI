import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type DragEvent,
} from "react";
import { ApiError, api, getToken, setToken } from "./api/client";
import type { DocumentOut, MeOut, ProfileUpdate, ThreadOut } from "./api/types";
import type { UiMessage } from "./components/ChatPanel";
import { ChatThread } from "./components/ChatThread";
import { Composer, readDroppedDocId } from "./components/Composer";
import { Sidebar } from "./components/Sidebar";
import { ThemeToggle } from "./components/ThemeToggle";
import { useSidebarWidth } from "./hooks/useSidebarWidth";
import { applyTheme, readTheme, writeTheme, type Theme } from "./theme";

function parseCitations(raw: string | null) {
  if (!raw) return [];
  try {
    return JSON.parse(raw) as UiMessage["citations"];
  } catch {
    return [];
  }
}

function shortName(name: string, max = 36): string {
  if (name.length <= max) return name;
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  const keep = Math.max(8, max - ext.length - 1);
  return `${name.slice(0, keep)}…${ext}`;
}

function toUiMessages(
  rows: Awaited<ReturnType<typeof api.messages>>,
): UiMessage[] {
  return rows.map((m) => ({
    id: m.id,
    role: m.role === "user" ? "user" : "assistant",
    content: m.content,
    refused: Boolean(m.refused),
    citations: m.role === "assistant" ? parseCitations(m.citations_json) : [],
  }));
}

export default function App() {
  const [bootError, setBootError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<MeOut | null>(null);
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [threads, setThreads] = useState<ThreadOut[]>([]);
  const [threadDocs, setThreadDocs] = useState<DocumentOut[]>([]);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  const [busyUpload, setBusyUpload] = useState(false);
  const [busySummary, setBusySummary] = useState(false);
  const [busyAsk, setBusyAsk] = useState(false);
  const [busyAuth, setBusyAuth] = useState(false);
  const [busyClear, setBusyClear] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { width: sidebarWidth, dragging, onResizeStart } = useSidebarWidth();
  const [theme, setTheme] = useState<Theme>(() => {
    const initial = readTheme();
    applyTheme(initial);
    return initial;
  });

  const chatReady = useMemo(
    () => threadDocs.some((d) => d.status === "ready"),
    [threadDocs],
  );

  const logoSrc =
    theme === "dark" ? "/brand/logo-dark.jpeg" : "/brand/logo-light.jpeg";

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    writeTheme(next);
    applyTheme(next);
  }

  const loadDocs = useCallback(async () => {
    const nextDocs = await api.documents();
    setDocs(nextDocs);
  }, []);

  const loadThreads = useCallback(async () => {
    const list = await api.threads(40);
    setThreads(list);
  }, []);

  const loadThreadDocs = useCallback(async (id: string) => {
    const attached = await api.threadDocuments(id);
    setThreadDocs(attached);
  }, []);

  // Refs keep startNewChat stable so ensureSession's boot effect does not re-fire.
  const threadIdRef = useRef(threadId);
  const messagesRef = useRef(messages);
  const meRef = useRef(me);
  useEffect(() => {
    threadIdRef.current = threadId;
  }, [threadId]);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  useEffect(() => {
    meRef.current = me;
  }, [me]);

  const discardDraftIfNoQuestion = useCallback(async () => {
    const draftId = threadIdRef.current;
    const hasUserQuestion = messagesRef.current.some((m) => m.role === "user");
    if (draftId && !hasUserQuestion) {
      try {
        await api.deleteThread(draftId);
      } catch {
        /* ignore */
      }
    }
  }, []);

  const startNewChat = useCallback(async () => {
    // Summary-only or empty drafts are not real chats — drop them from history.
    await discardDraftIfNoQuestion();
    setThreadId(null);
    threadIdRef.current = null;
    setThreadDocs([]);
    setMessages([]);
    setChatError(null);
    const profile = meRef.current;
    if (profile && !profile.is_guest) {
      try {
        await loadThreads();
      } catch {
        /* ignore */
      }
    }
  }, [discardDraftIfNoQuestion, loadThreads]);

  const ensureThreadId = useCallback(async () => {
    if (threadIdRef.current) return threadIdRef.current;
    const thread = await api.createThread();
    setThreadId(thread.id);
    threadIdRef.current = thread.id;
    return thread.id;
  }, []);

  const ensureSession = useCallback(async () => {
    const existing = getToken();
    if (existing) {
      try {
        const profile = await api.me();
        setMe(profile);

        if (profile.is_guest) {
          try {
            await api.clearLibrary();
          } catch {
            /* ignore */
          }
          setDocs([]);
          setThreads([]);
          setUploadNote(null);
          await startNewChat();
          return;
        }

        await loadDocs();
        await loadThreads();
        await startNewChat();
        return;
      } catch {
        setToken(null);
      }
    }

    const guest = await api.guest();
    setToken(guest.token);
    const profile = await api.me();
    setMe(profile);
    setDocs([]);
    setThreads([]);
    await startNewChat();
  }, [loadDocs, loadThreads, startNewChat]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await ensureSession();
        if (!cancelled) setReady(true);
      } catch (err) {
        if (!cancelled) {
          setBootError(
            err instanceof Error
              ? err.message
              : "Could not reach the DocCite API. Is it running?",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ensureSession]);

  async function handleUpload(files: FileList) {
    setBusyUpload(true);
    setUploadNote(`Uploading ${files.length} file(s)…`);
    const notes: string[] = [];
    try {
      const tid = await ensureThreadId();
      for (const file of Array.from(files)) {
        try {
          const doc = await api.upload(file, tid);
          const label = shortName(doc.filename);
          notes.push(
            doc.status === "ready"
              ? `✓ ${label} attached (${doc.chunk_count} chunks)`
              : `✗ ${label}: ${doc.error || doc.status}`,
          );
        } catch (err) {
          notes.push(
            `✗ ${shortName(file.name)}: ${
              err instanceof Error ? err.message : "Upload failed"
            }`,
          );
        }
      }
      await loadDocs();
      await loadThreadDocs(tid);
      if (me && !me.is_guest) await loadThreads();
      setUploadNote(notes.join(" · ") || "Upload finished.");
      // Fresh upload into a draft: open that document's summary in chat.
      const readyUploaded = notes.some((n) => n.startsWith("✓"));
      if (readyUploaded && !messagesRef.current.some((m) => m.role === "user")) {
        const attached = await api.threadDocuments(tid);
        const lastReady = [...attached].reverse().find((d) => d.status === "ready");
        if (lastReady) await showDocSummaryInChat(tid, lastReady);
      }
    } finally {
      setBusyUpload(false);
    }
  }

  async function showDocSummaryInChat(tid: string, doc: DocumentOut) {
    setBusySummary(true);
    setChatError(null);
    try {
      const summary = await api.documentSummary(doc.id, false);
      setMessages([
        {
          id: `summary-${doc.id}`,
          role: "assistant",
          content: `Summary of ${doc.filename}\n\n${summary.text}`,
          citations: [],
        },
      ]);
      setSidebarOpen(false);
    } catch (err) {
      setChatError(
        err instanceof Error ? err.message : "Could not load document summary",
      );
    } finally {
      setBusySummary(false);
    }
  }

  async function handleOpenDocSummary(docId: string) {
    const doc = docs.find((d) => d.id === docId);
    if (!doc || doc.status !== "ready") return;

    await discardDraftIfNoQuestion();
    setThreadId(null);
    threadIdRef.current = null;
    setThreadDocs([]);
    setMessages([]);
    setChatError(null);
    setBusySummary(true);

    try {
      const thread = await api.createThread();
      setThreadId(thread.id);
      threadIdRef.current = thread.id;
      const attached = await api.attachDocuments(thread.id, [docId]);
      setThreadDocs(attached);
      await showDocSummaryInChat(thread.id, doc);
      // Not a registered chat until the user asks a follow-up.
      if (me && !me.is_guest) await loadThreads();
    } catch (err) {
      setChatError(
        err instanceof Error ? err.message : "Could not open document summary",
      );
      setBusySummary(false);
    }
  }

  async function handleDropDocIds(docIds: string[]) {
    if (!docIds.length) return;
    const tid = await ensureThreadId();
    try {
      const attached = await api.attachDocuments(tid, docIds);
      setThreadDocs(attached);
      setUploadNote(
        docIds.length === 1
          ? "Document attached to this chat."
          : `${docIds.length} documents attached to this chat.`,
      );
      if (me && !me.is_guest) await loadThreads();
    } catch (err) {
      setUploadNote(
        `✗ Attach failed: ${err instanceof Error ? err.message : "unknown error"}`,
      );
    }
  }

  async function handleDropDocOnThread(targetThreadId: string, docId: string) {
    try {
      await api.attachDocuments(targetThreadId, [docId]);
      if (targetThreadId === threadId) {
        await loadThreadDocs(targetThreadId);
      } else {
        // Switch into that chat so the attach is visible.
        await handleSelectThread(targetThreadId);
      }
      setUploadNote("Document attached to chat.");
      if (me && !me.is_guest) await loadThreads();
    } catch (err) {
      setUploadNote(
        `✗ Attach failed: ${err instanceof Error ? err.message : "unknown error"}`,
      );
    }
  }

  const [mainDragOver, setMainDragOver] = useState(false);

  function handleMainDragOver(e: DragEvent) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setMainDragOver(true);
  }

  function handleMainDrop(e: DragEvent) {
    e.preventDefault();
    setMainDragOver(false);
    const id = readDroppedDocId(e.dataTransfer);
    if (id) {
      void handleDropDocIds([id]);
      return;
    }
    if (e.dataTransfer.files?.length) {
      void handleUpload(e.dataTransfer.files);
    }
  }

  async function handleDetach(docId: string) {
    if (!threadId) return;
    await api.detachDocument(threadId, docId);
    await loadThreadDocs(threadId);
    if (me && !me.is_guest) await loadThreads();
  }

  async function handleAsk(question: string) {
    if (!threadId || !chatReady) {
      setChatError("Attach a document to this chat before asking.");
      return;
    }
    setChatError(null);
    const tempId = `local-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: tempId, role: "user", content: question },
    ]);
    setBusyAsk(true);
    try {
      const result = await api.ask(question, threadId);
      setThreadId(result.thread_id);
      setMessages((prev) => [
        ...prev,
        {
          id: `${tempId}-a`,
          role: "assistant",
          content: result.answer.text,
          refused: result.answer.refused,
          citations: result.answer.citations ?? [],
        },
      ]);
      if (me && !me.is_guest) await loadThreads();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Ask failed";
      setChatError(msg);
      setMessages((prev) => [
        ...prev,
        {
          id: `${tempId}-err`,
          role: "assistant",
          content: msg,
          refused: true,
          citations: [],
        },
      ]);
    } finally {
      setBusyAsk(false);
    }
  }

  async function afterAuth(token: string) {
    setToken(token);
    setAuthError(null);
    const profile = await api.me();
    setMe(profile);
    await loadDocs();
    await loadThreads();
    await startNewChat();
  }

  async function handleLogin(email: string, password: string) {
    setBusyAuth(true);
    setAuthError(null);
    try {
      const session = await api.login(email, password);
      await afterAuth(session.token);
    } catch (err) {
      setAuthError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setBusyAuth(false);
    }
  }

  async function handleRegister(email: string, password: string) {
    setBusyAuth(true);
    setAuthError(null);
    try {
      const session = await api.register(email, password);
      await afterAuth(session.token);
    } catch (err) {
      setAuthError(err instanceof ApiError ? err.message : "Register failed");
    } finally {
      setBusyAuth(false);
    }
  }

  async function handleLogout() {
    setBusyAuth(true);
    try {
      try {
        await api.logout();
      } catch {
        /* ignore */
      }
      setToken(null);
      const guest = await api.guest();
      setToken(guest.token);
      const profile = await api.me();
      setMe(profile);
      setDocs([]);
      setThreads([]);
      setUploadNote(null);
      await startNewChat();
    } finally {
      setBusyAuth(false);
    }
  }

  async function handleClear() {
    setBusyClear(true);
    try {
      await api.clearLibrary();
      setDocs([]);
      setThreads([]);
      setUploadNote(null);
      await startNewChat();
    } finally {
      setBusyClear(false);
    }
  }

  async function handleDeleteDoc(docId: string) {
    await api.deleteDocument(docId);
    await loadDocs();
    if (threadId) await loadThreadDocs(threadId);
    setUploadNote("Document removed.");
  }

  async function handleSaveProfile(body: ProfileUpdate) {
    const updated = await api.updateProfile(body);
    setMe(updated);
  }

  async function handleNewChat() {
    await startNewChat();
    setSidebarOpen(false);
    setUploadNote(null);
    if (me && !me.is_guest) await loadThreads();
  }

  async function handleSelectThread(id: string) {
    setChatError(null);
    setBusyAsk(true);
    try {
      const [rows, attached] = await Promise.all([
        api.messages(100, id),
        api.threadDocuments(id),
      ]);
      setMessages(toUiMessages(rows));
      setThreadDocs(attached);
      setThreadId(id);
      setSidebarOpen(false);
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Could not load chat");
    } finally {
      setBusyAsk(false);
    }
  }

  async function handleDeleteThread(id: string) {
    await api.deleteThread(id);
    if (threadId === id) {
      await startNewChat();
    }
    await loadThreads();
  }

  if (bootError) {
    return (
      <div className="boot-screen">
        <ThemeToggle theme={theme} onToggle={toggleTheme} />
        <img src={logoSrc} alt="DocCite" className="boot-logo" />
        <h1>Cannot reach API</h1>
        <p>{bootError}</p>
        <p className="muted">
          Run <code>API_PORT=8001 python scripts/run_api.py</code> and set{" "}
          <code>VITE_API_BASE_URL</code> if needed.
        </p>
      </div>
    );
  }

  if (!ready || !me) {
    return (
      <div className="boot-screen">
        <img src={logoSrc} alt="DocCite" className="boot-logo" />
        <p className="muted">Starting session…</p>
      </div>
    );
  }

  const empty = messages.length === 0 && !busySummary && !busyAsk;

  return (
    <div
      className={`app-shell${dragging ? " resizing" : ""}`}
      style={
        {
          ["--sidebar-width"]: `${sidebarWidth}px`,
        } as CSSProperties
      }
    >
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        logoSrc={logoSrc}
        docs={docs}
        threads={threads}
        activeThreadId={threadId}
        summaryBusy={busySummary}
        uploadBusy={busyUpload}
        uploadNote={uploadNote}
        clearBusy={busyClear}
        authBusy={busyAuth}
        authError={authError}
        isGuest={me.is_guest}
        me={me}
        onUpload={handleUpload}
        onNewChat={() => void handleNewChat()}
        onSelectThread={(id) => void handleSelectThread(id)}
        onDeleteThread={handleDeleteThread}
        onDeleteDoc={handleDeleteDoc}
        onOpenDocSummary={handleOpenDocSummary}
        onDropDocOnThread={handleDropDocOnThread}
        onClear={handleClear}
        onLogin={handleLogin}
        onRegister={handleRegister}
        onLogout={handleLogout}
        onSaveProfile={handleSaveProfile}
      />

      <div
        className="sidebar-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sidebar"
        onPointerDown={onResizeStart}
        onMouseDown={onResizeStart}
      />

      <div
        className={`main-pane${mainDragOver ? " drop-target" : ""}`}
        onDragOver={handleMainDragOver}
        onDragLeave={(e) => {
          if (e.currentTarget.contains(e.relatedTarget as Node)) return;
          setMainDragOver(false);
        }}
        onDrop={handleMainDrop}
      >
        <header className="main-top">
          <button
            type="button"
            className="icon-btn mobile-only"
            aria-label="Open sidebar"
            onClick={() => setSidebarOpen(true)}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path
                d="M4 7h16M4 12h16M4 17h16"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <span className="main-title">DocCite</span>
          <div className="main-top-actions">
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
        </header>

        {me.is_guest && me.guest_notice ? (
          <div className="guest-strip" role="status">
            {me.guest_notice}
          </div>
        ) : null}

        <div className={`chat-stage${empty ? " empty" : ""}`}>
          {empty ? (
            <div className="empty-hero">
              <h1>What&apos;s in this chat&apos;s documents?</h1>
              <p className="muted">
                Click a Library file to open its summary here, or upload / drag
                files into this chat. Ask a follow-up to save it under Recents.
              </p>
              {!chatReady ? (
                <p className="hint">
                  Use <strong>+</strong> below, or click / drag a Library file into
                  this chat (or onto a Recents item).
                </p>
              ) : null}
            </div>
          ) : (
            <ChatThread
              messages={messages}
              busy={busyAsk || busySummary}
              busyLabel={
                busySummary
                  ? "Summarizing this document…"
                  : "Searching your documents…"
              }
            />
          )}
        </div>

        <div className="composer-dock">
          {chatError ? <p className="error dock-error">{chatError}</p> : null}
          <Composer
            busy={busyAsk || busySummary}
            disabled={!chatReady || busySummary}
            uploadBusy={busyUpload}
            threadDocs={threadDocs}
            onAsk={handleAsk}
            onUpload={handleUpload}
            onDetach={handleDetach}
          />
          <p className="disclaimer">
            DocCite answers only from documents attached to this chat.
          </p>
        </div>
      </div>
    </div>
  );
}
