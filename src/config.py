"""Typed settings loaded from environment / `.env`."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root: …/DocCite (parent of `src/`)
REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration for DocCite.

    Values come from environment variables or a `.env` file at the repo root.
    Field names map to UPPER_SNAKE env vars (e.g. `openai_api_key` → OPENAI_API_KEY).
    """

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    # Speech-to-text: gpt-4o-mini-transcribe | gpt-4o-transcribe | whisper-1
    openai_transcribe_model: str = "gpt-4o-mini-transcribe"

    chunk_size: int = 800
    chunk_overlap: int = 150
    retrieve_top_k: int = 6
    similarity_threshold: float = 0.25

    data_dir: Path = REPO_ROOT / "data"
    chroma_dir: Path = REPO_ROOT / "data" / "chroma"
    upload_dir: Path = REPO_ROOT / "data" / "uploads"
    collection_name: str = "doccite_mvp"

    # Step 7 — API / multi-user
    database_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'doccite.db').as_posix()}"
    guest_inactivity_ttl_hours: int = 24
    auth_secret: str = "dev-change-me"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Comma-separated browser origins (Vite local + Vercel). Empty = deny cross-origin.
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173"
    )
    # Optional regex for preview deploys, e.g. https://.*\\.vercel\\.app
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    def model_post_init(self, __context: object) -> None:
        """Resolve relative paths against the repo root (not the shell cwd)."""
        self.data_dir = _resolve_path(self.data_dir)
        self.chroma_dir = _resolve_path(self.chroma_dir)
        self.upload_dir = _resolve_path(self.upload_dir)
        if self.database_url.startswith("sqlite:///./"):
            rel = self.database_url.removeprefix("sqlite:///./")
            self.database_url = f"sqlite:///{(REPO_ROOT / rel).resolve().as_posix()}"

    def ensure_data_dirs(self) -> None:
        """Create local data folders if missing (uploads, chroma, data root)."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


def _resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


settings = Settings()
settings.ensure_data_dirs()
