"""DocCite Streamlit UI — upload, summarize, ask with citations."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingest.pipeline import ingest_file
from src.logging_setup import setup_logging
from src.models import Citation
from src.rag.qa import QaError, answer
from src.rag.summarize import summarize_library
from src.store import registry
from src.store.reset import reset_library
from src.ui.helpers import (
    answer_to_message,
    citation_lines,
    format_doc_row,
    safe_error_message,
)

setup_logging()

st.set_page_config(page_title="DocCite", page_icon="📄", layout="wide")

MAX_CHAT_MESSAGES = 40  # keep last N messages in the transcript


def _init_state() -> None:
    if "chat" not in st.session_state:
        st.session_state.chat = []
    if "summary_text" not in st.session_state:
        st.session_state.summary_text = None
    if "last_ingest_note" not in st.session_state:
        st.session_state.last_ingest_note = ""


def _ready_docs():
    return [d for d in registry.list_documents() if d.status == "ready"]


def _refresh_summary(*, force: bool = False) -> None:
    try:
        result = summarize_library(force=force)
        st.session_state.summary_text = result.text
    except Exception as exc:  # noqa: BLE001
        st.session_state.summary_text = f"(Summary unavailable: {safe_error_message(exc)})"


def _ingest_uploads(files) -> None:
    notes: list[str] = []
    for uploaded in files:
        suffix = Path(uploaded.name).suffix.lower() or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)
        try:
            with st.spinner(f"Processing {uploaded.name}…"):
                result = ingest_file(tmp_path)
            doc = result.document
            notes.append(f"✓ {doc.filename} → {doc.status} ({doc.chunk_count} chunks)")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"✗ {uploaded.name}: {safe_error_message(exc)}")
        finally:
            tmp_path.unlink(missing_ok=True)
    st.session_state.last_ingest_note = "\n".join(notes)
    _refresh_summary(force=True)


def _render_citations(raw_citations: list[dict]) -> None:
    if not raw_citations:
        return
    cites = [Citation.model_validate(c) for c in raw_citations]
    with st.expander(f"Citations ({len(cites)})", expanded=True):
        for line in citation_lines(cites):
            st.markdown(line)


def main() -> None:
    _init_state()

    st.title("DocCite")
    st.caption(
        "Ask questions answered only from your uploaded documents — with citations."
    )

    # ----- Sidebar -----
    with st.sidebar:
        st.header("Library")
        uploads = st.file_uploader(
            "Upload documents",
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True,
            help="Max 25 MB per file. PDF, DOCX, TXT, MD.",
        )
        if st.button("Process uploads", type="primary", disabled=not uploads):
            _ingest_uploads(uploads)
            st.rerun()

        if st.session_state.last_ingest_note:
            st.caption(st.session_state.last_ingest_note)

        st.subheader("Documents")
        docs = sorted(registry.list_documents(), key=lambda d: d.filename.lower())
        if not docs:
            st.info("No documents yet. Upload to begin.")
        else:
            for doc in docs:
                st.markdown(format_doc_row(doc))
                st.divider()

        st.subheader("Danger zone")
        confirm = st.checkbox("I understand this deletes the whole library")
        if st.button("Clear library", disabled=not confirm):
            with st.spinner("Clearing library…"):
                reset_library()
            st.session_state.chat = []
            st.session_state.summary_text = None
            st.session_state.last_ingest_note = ""
            st.success("Library cleared.")
            st.rerun()

    # ----- Main: summary -----
    ready = _ready_docs()
    st.subheader("Library summary")
    if st.session_state.summary_text is None and ready:
        with st.spinner("Generating summary…"):
            _refresh_summary(force=False)
    if not ready:
        st.info("Upload documents to get a summary.")
    elif st.session_state.summary_text:
        st.markdown(st.session_state.summary_text)
        if st.button("Refresh summary"):
            with st.spinner("Regenerating summary…"):
                _refresh_summary(force=True)
            st.rerun()

    # ----- Main: chat -----
    st.subheader("Chat")
    # Cap display
    visible = st.session_state.chat[-MAX_CHAT_MESSAGES:]
    for msg in visible:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and msg.get("refused"):
                st.warning(msg["content"])
            else:
                st.markdown(msg["content"])
            if msg["role"] == "assistant":
                _render_citations(msg.get("citations") or [])

    prompt = st.chat_input(
        "Ask a question about your documents…",
        disabled=not ready,
    )
    if not ready:
        st.caption("Ask is disabled until at least one document is ready.")

    if prompt:
        question = prompt.strip()
        if not question:
            st.error("Question is empty.")
            return

        st.session_state.chat.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            try:
                with st.spinner("Searching your documents…"):
                    result = answer(question)
                payload = answer_to_message(result)
                st.session_state.chat.append(payload)
                if result.refused:
                    st.warning(result.text)
                else:
                    st.markdown(result.text)
                _render_citations(payload["citations"])
            except QaError as exc:
                err = safe_error_message(exc)
                st.error(err)
                st.session_state.chat.append(
                    {
                        "role": "assistant",
                        "content": err,
                        "refused": True,
                        "citations": [],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                err = safe_error_message(exc)
                st.error(err)
                st.session_state.chat.append(
                    {
                        "role": "assistant",
                        "content": err,
                        "refused": True,
                        "citations": [],
                    }
                )


if __name__ == "__main__":
    main()
