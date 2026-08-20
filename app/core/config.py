from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Project
    PROJECT_NAME: str = "LongWall AI"
    API_V1_STR: str = "/api/v1"

    # MongoDB (Atlas or local)
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "griffsox_db"

    # Judge SLM mode: "heuristic" | "ollama" | "gemini"
    JUDGE_MODE: str = "heuristic"
    JUDGE_OLLAMA_URL: str = "http://localhost:11434/api/generate"
    JUDGE_OLLAMA_MODEL: str = "llama3"
    JUDGE_GEMINI_API_KEY: Optional[str] = None
    JUDGE_GEMINI_MODEL: str = "gemini-2.0-flash"
    JUDGE_TIMEOUT: float = 5.0

    # SOAR Containment endpoints (all optional — skipped gracefully when unset)
    LANGGRAPH_INTERRUPT_URL: Optional[str] = None
    STS_REVOKE_URL: Optional[str] = None
    DOCKER_EVICT_URL: Optional[str] = None

    # SIEM
    SIEM_WEBHOOK_URL: Optional[str] = None

    # Action Guardrail Settings (PS-3.1)
    ACTION_RULES_PATH: str = "action_rules.yaml"
    DRY_RUN: bool = False

    # RBAC policy file (JSON) — falls back to DEFAULT_POLICIES when unset
    RBAC_POLICY_PATH: Optional[str] = None

    # Telemetry event TTL (days) — MongoDB TTL index
    TELEMETRY_TTL_DAYS: int = 30

    # CORS — comma-separated list of allowed origins for production
    # Example: https://griffsox.vercel.app,https://griffsox.com
    ALLOWED_ORIGINS: str = ""

    # SQLite finance DB path — override for persistent volume on AWS
    # Default: <project_root>/data/finance_records.db
    FINANCE_DB_PATH: Optional[str] = None


settings = Settings()
