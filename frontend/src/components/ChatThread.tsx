import { useEffect, useRef } from "react";
import type { Citation } from "../api/types";
import type { UiMessage } from "./ChatPanel";

export type { UiMessage };

function Citations({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <details className="citations">
      <summary>Citations ({citations.length})</summary>
      <ol>
        {citations.map((c, i) => (
          <li key={`${c.chunk_id}-${i}`}>
            <code>{c.filename}</code>
            <span className="cite-meta"> · page {c.page ?? "n/a"}</span>
            <blockquote>{c.quote}</blockquote>
          </li>
        ))}
      </ol>
    </details>
  );
}

type Props = {
  messages: UiMessage[];
  busy: boolean;
  busyLabel?: string;
};

export function ChatThread({
  messages,
  busy,
  busyLabel = "Searching your documents…",
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const end = endRef.current;
    if (!end) return;
    const stage = end.closest(".chat-stage");
    // Jump to latest message after ask / reply (chat-stage is the scroller).
    requestAnimationFrame(() => {
      if (stage instanceof HTMLElement) {
        stage.scrollTop = stage.scrollHeight;
      } else {
        end.scrollIntoView({ behavior: "smooth", block: "end" });
      }
    });
  }, [messages, busy]);

  return (
    <div className="thread" aria-live="polite">
      {messages.map((m) => (
        <article
          key={m.id}
          className={`msg msg-${m.role}${m.refused ? " refused" : ""}`}
        >
          <div className="msg-avatar" aria-hidden="true">
            {m.role === "user" ? "You" : "DC"}
          </div>
          <div className="msg-body">
            <p className="msg-text">{m.content}</p>
            {m.role === "assistant" && m.citations ? (
              <Citations citations={m.citations} />
            ) : null}
          </div>
        </article>
      ))}
      {busy ? (
        <article className="msg msg-assistant">
          <div className="msg-avatar" aria-hidden="true">
            DC
          </div>
          <div className="msg-body">
            <p className="typing">{busyLabel}</p>
          </div>
        </article>
      ) : null}
      <div ref={endRef} className="thread-end" aria-hidden="true" />
    </div>
  );
}
