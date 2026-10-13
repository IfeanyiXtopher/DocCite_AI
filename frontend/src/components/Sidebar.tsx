import { useEffect, useRef, useState, type FormEvent } from "react";
import type { DocumentOut, MeOut, ProfileUpdate, ThreadOut } from "../api/types";
import { lookslikeDocId } from "./Composer";

type Props = {
  open: boolean;
  onClose: () => void;
  logoSrc: string;
  docs: DocumentOut[];
  threads: ThreadOut[];
  activeThreadId: string | null;
  summaryBusy: boolean;
  uploadBusy: boolean;
  uploadNote: string | null;
  clearBusy: boolean;
  authBusy: boolean;
  authError: string | null;
  isGuest: boolean;
  me: MeOut;
  onUpload: (files: FileList) => Promise<void>;
  onNewChat: () => void;
  onSelectThread: (threadId: string) => void;
  onDeleteThread: (threadId: string) => Promise<void>;
  onDeleteDoc: (docId: string) => Promise<void>;
  onOpenDocSummary: (docId: string) => Promise<void>;
  onDropDocOnThread: (threadId: string, docId: string) => Promise<void>;
  onClear: () => Promise<void>;
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (email: string, password: string) => Promise<void>;
  onLogout: () => Promise<void>;
  onSaveProfile: (body: ProfileUpdate) => Promise<void>;
};

const ACCEPT = ".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown";

function initials(label: string): string {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export function Sidebar({
  open,
  onClose,
  logoSrc,
  docs,
  threads,
  activeThreadId,
  summaryBusy,
  uploadBusy,
  uploadNote,
  clearBusy,
  authBusy,
  authError,
  isGuest,
  me,
  onUpload,
  onNewChat,
  onSelectThread,
  onDeleteThread,
  onDeleteDoc,
  onOpenDocSummary,
  onDropDocOnThread,
  onClear,
  onLogin,
  onRegister,
  onLogout,
  onSaveProfile,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [formEmail, setFormEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmClear, setConfirmClear] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileName, setProfileName] = useState(me.display_name ?? "");
  const [profileTitle, setProfileTitle] = useState(me.title ?? "");
  const [profileCompany, setProfileCompany] = useState(me.company ?? "");
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null);
  const [recentsOpen, setRecentsOpen] = useState(() =>
    localStorage.getItem("doccite_recents_open") !== "0",
  );
  const [libraryOpen, setLibraryOpen] = useState(() =>
    localStorage.getItem("doccite_library_open") !== "0",
  );

  const label = me.display_name?.trim() || me.email || "Account";

  function toggleRecents() {
    setRecentsOpen((v) => {
      const next = !v;
      localStorage.setItem("doccite_recents_open", next ? "1" : "0");
      return next;
    });
  }

  function toggleLibrary() {
    setLibraryOpen((v) => {
      const next = !v;
      localStorage.setItem("doccite_library_open", next ? "1" : "0");
      return next;
    });
  }

  useEffect(() => {
    setProfileName(me.display_name ?? "");
    setProfileTitle(me.title ?? "");
    setProfileCompany(me.company ?? "");
  }, [me.display_name, me.title, me.company]);

  useEffect(() => {
    if (!menuOpen) return;
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [menuOpen]);

  async function handleFiles() {
    const files = fileRef.current?.files;
    if (!files?.length) return;
    await onUpload(files);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function handleAuth(e: FormEvent) {
    e.preventDefault();
    if (authMode === "login") await onLogin(formEmail, password);
    else await onRegister(formEmail, password);
  }

  async function handleProfileSave(e: FormEvent) {
    e.preventDefault();
    setProfileBusy(true);
    setProfileError(null);
    try {
      await onSaveProfile({
        display_name: profileName,
        title: profileTitle,
        company: profileCompany,
      });
      setProfileOpen(false);
      setMenuOpen(false);
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "Could not save profile");
    } finally {
      setProfileBusy(false);
    }
  }

  async function handleDeleteDoc(id: string, filename: string) {
    if (!window.confirm(`Delete “${filename}” from your library?`)) return;
    setDeletingId(id);
    try {
      await onDeleteDoc(id);
    } finally {
      setDeletingId(null);
    }
  }

  async function handleDeleteThread(id: string, title: string) {
    if (!window.confirm(`Delete chat “${title}”?`)) return;
    setDeletingThreadId(id);
    try {
      await onDeleteThread(id);
    } finally {
      setDeletingThreadId(null);
    }
  }

  return (
    <>
      <div
        className={`sidebar-backdrop${open ? " open" : ""}`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside className={`sidebar${open ? " open" : ""}`}>
        <div className="sidebar-top">
          <div className="brand-row">
            <img src={logoSrc} alt="DocCite" className="brand-mark" />
            <button
              type="button"
              className="icon-btn mobile-only"
              aria-label="Close sidebar"
              onClick={onClose}
            >
              ✕
            </button>
          </div>

          <button type="button" className="new-chat" onClick={onNewChat}>
            <span className="plus" aria-hidden="true">
              +
            </span>
            New chat
          </button>

          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            multiple
            className="sr-only"
            disabled={uploadBusy}
            onChange={() => void handleFiles()}
          />
          <button
            type="button"
            className="nav-item"
            disabled={uploadBusy}
            onClick={() => fileRef.current?.click()}
          >
            {uploadBusy ? "Uploading…" : "Upload documents"}
          </button>
          {uploadNote ? (
            <p
              className={`upload-note${uploadNote.includes("✗") ? " error" : ""}`}
              title={uploadNote}
            >
              {uploadNote}
            </p>
          ) : null}
        </div>

        <div className="sidebar-mid">
          {!isGuest ? (
            <section className="sidebar-section">
              <button
                type="button"
                className="sidebar-section-toggle"
                aria-expanded={recentsOpen}
                onClick={toggleRecents}
              >
                <span className="sidebar-label">Recents</span>
                <span className="section-count" aria-hidden="true">
                  {threads.length}
                </span>
                <svg
                  className={`section-chevron${recentsOpen ? " open" : ""}`}
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M9 6l6 6-6 6"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              {recentsOpen ? (
                !threads.length ? (
                  <p className="muted tiny">No recent chats yet.</p>
                ) : (
                  <ul className="recent-nav">
                    {threads.map((t) => (
                      <li key={t.id}>
                        <div
                          className={
                            t.id === activeThreadId
                              ? "recent-row active"
                              : "recent-row"
                          }
                          onDragOver={(e) => {
                            e.preventDefault();
                            e.dataTransfer.dropEffect = "copy";
                            e.currentTarget.classList.add("drop-target");
                          }}
                          onDragLeave={(e) => {
                            e.currentTarget.classList.remove("drop-target");
                          }}
                          onDrop={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            e.currentTarget.classList.remove("drop-target");
                            const custom = e.dataTransfer
                              .getData("application/x-doccite-doc")
                              .trim();
                            const plain = e.dataTransfer
                              .getData("text/plain")
                              .trim();
                            const id = lookslikeDocId(custom)
                              ? custom
                              : lookslikeDocId(plain)
                                ? plain
                                : "";
                            if (id) void onDropDocOnThread(t.id, id);
                          }}
                        >
                          <button
                            type="button"
                            className="recent-item"
                            title={t.title}
                            onClick={() => onSelectThread(t.id)}
                          >
                            {t.title}
                          </button>
                          <button
                            type="button"
                            className="doc-delete"
                            disabled={deletingThreadId === t.id}
                            aria-label={`Delete chat ${t.title}`}
                            onClick={() =>
                              void handleDeleteThread(t.id, t.title)
                            }
                          >
                            {deletingThreadId === t.id ? "…" : "✕"}
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )
              ) : null}
            </section>
          ) : null}

          <section className="sidebar-section">
            <button
              type="button"
              className="sidebar-section-toggle"
              aria-expanded={libraryOpen}
              onClick={toggleLibrary}
            >
              <span className="sidebar-label">Library</span>
              <span className="section-count" aria-hidden="true">
                {docs.length}
              </span>
              <svg
                className={`section-chevron${libraryOpen ? " open" : ""}`}
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M9 6l6 6-6 6"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
            {libraryOpen ? (
              !docs.length ? (
                <p className="muted tiny">No documents yet.</p>
              ) : (
                <ul className="doc-nav">
                  {docs.map((d) => (
                    <li
                      key={d.id}
                      title={`${d.filename} — click for summary, drag to attach`}
                    >
                      <div className="doc-item">
                        <button
                          type="button"
                          className="doc-attach"
                          disabled={d.status !== "ready" || summaryBusy}
                          draggable={d.status === "ready"}
                          title="Click to open summary in chat, or drag to attach"
                          onClick={() => void onOpenDocSummary(d.id)}
                          onDragStart={(e) => {
                            e.dataTransfer.setData("text/plain", d.id);
                            e.dataTransfer.setData(
                              "application/x-doccite-doc",
                              d.id,
                            );
                            e.dataTransfer.effectAllowed = "copy";
                            e.currentTarget.classList.add("dragging");
                          }}
                          onDragEnd={(e) => {
                            e.currentTarget.classList.remove("dragging");
                          }}
                        >
                          <span className="doc-name">{d.filename}</span>
                          <span className={`status-dot ${d.status}`} />
                        </button>
                        <button
                          type="button"
                          className="doc-delete"
                          disabled={deletingId === d.id}
                          aria-label={`Delete ${d.filename}`}
                          onClick={() => void handleDeleteDoc(d.id, d.filename)}
                        >
                          {deletingId === d.id ? "…" : "✕"}
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )
            ) : null}
          </section>
        </div>

        <div className="sidebar-bottom">
          {!isGuest && me.email ? (
            <div className="account-menu-wrap" ref={menuRef}>
              <button
                type="button"
                className="account-chip account-trigger"
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((v) => !v)}
              >
                <span className="avatar" aria-hidden="true">
                  {initials(label)}
                </span>
                <span className="account-text">
                  <strong className="account-name" title={label}>
                    {label}
                  </strong>
                  <span className="muted tiny account-sub" title={me.email}>
                    {me.display_name?.trim() ? me.email : "Signed in"}
                  </span>
                </span>
              </button>

              {menuOpen ? (
                <div className="account-dropdown" role="menu">
                  <div className="account-dropdown-head">
                    <strong title={label}>{label}</strong>
                    <span className="muted tiny" title={me.email ?? undefined}>
                      {me.email}
                    </span>
                  </div>
                  <button
                    type="button"
                    role="menuitem"
                    className="account-menu-item"
                    onClick={() => {
                      setProfileOpen(true);
                      setMenuOpen(false);
                    }}
                  >
                    Profile
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="account-menu-item"
                    disabled={authBusy}
                    onClick={() => {
                      setMenuOpen(false);
                      void onLogout();
                    }}
                  >
                    Log out
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <>
              <button
                type="button"
                className="nav-item"
                onClick={() => setShowAuth((v) => !v)}
              >
                {showAuth ? "Hide account" : "Log in / Register"}
              </button>
              {showAuth ? (
                <form className="sidebar-card auth-form" onSubmit={(e) => void handleAuth(e)}>
                  <div className="auth-tabs">
                    <button
                      type="button"
                      className={authMode === "login" ? "tab active" : "tab"}
                      onClick={() => setAuthMode("login")}
                    >
                      Log in
                    </button>
                    <button
                      type="button"
                      className={authMode === "register" ? "tab active" : "tab"}
                      onClick={() => setAuthMode("register")}
                    >
                      Register
                    </button>
                  </div>
                  <input
                    type="email"
                    required
                    placeholder="Email"
                    value={formEmail}
                    onChange={(e) => setFormEmail(e.target.value)}
                  />
                  <input
                    type="password"
                    required
                    minLength={8}
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  {authError ? <p className="error">{authError}</p> : null}
                  <button type="submit" className="btn-block" disabled={authBusy}>
                    {authBusy
                      ? "Working…"
                      : authMode === "login"
                        ? "Log in"
                        : "Create account"}
                  </button>
                </form>
              ) : null}
            </>
          )}

          <label className="clear-row">
            <input
              type="checkbox"
              checked={confirmClear}
              onChange={(e) => setConfirmClear(e.target.checked)}
            />
            <span>Allow clear library</span>
          </label>
          <button
            type="button"
            className="danger-btn"
            disabled={!confirmClear || clearBusy}
            onClick={() => void onClear()}
          >
            {clearBusy ? "Clearing…" : "Clear library"}
          </button>
        </div>
      </aside>

      {profileOpen ? (
        <div className="modal-backdrop" onClick={() => setProfileOpen(false)}>
          <form
            className="modal-card"
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => void handleProfileSave(e)}
          >
            <h2>Profile</h2>
            <p className="muted tiny">Update how your name appears in DocCite.</p>
            <label>
              Display name
              <input
                value={profileName}
                onChange={(e) => setProfileName(e.target.value)}
                placeholder="Your name"
                maxLength={120}
              />
            </label>
            <label>
              Title
              <input
                value={profileTitle}
                onChange={(e) => setProfileTitle(e.target.value)}
                placeholder="e.g. Software Engineer"
                maxLength={160}
              />
            </label>
            <label>
              Company
              <input
                value={profileCompany}
                onChange={(e) => setProfileCompany(e.target.value)}
                placeholder="Optional"
                maxLength={160}
              />
            </label>
            {profileError ? <p className="error">{profileError}</p> : null}
            <div className="modal-actions">
              <button type="button" className="btn ghost" onClick={() => setProfileOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn-block" disabled={profileBusy}>
                {profileBusy ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}
