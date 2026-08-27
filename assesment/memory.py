"""Persistent SQLite3 + Hybrid (Semantic & Lexical) memory layer for agentic systems.

This module provides persistent cross-session episodic and preference storage backed by
standard library SQLite3, combined with hybrid retrieval via dense embedding cosine
similarity and lexical fuzzy matching (`difflib.SequenceMatcher`).
"""

from __future__ import annotations

import difflib
import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MemoryEntry:
    """Individual record representing an episodic or preference memory."""

    key: str
    value: Any
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert entry into standard dictionary representation."""
        data = asdict(self)
        data.pop("embedding", None)
        return data


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two float vectors in pure Python.

    Args:
        vec_a: First dense vector.
        vec_b: Second dense vector.

    Returns:
        Cosine similarity score bounded between -1.0 and 1.0 (or 0.0 if zero norm).
    """
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class AgentMemory:
    """Persistent SQLite3-backed memory store with Hybrid (Semantic + Lexical) retrieval."""

    def __init__(self, db_path: str = "agent_memory.db") -> None:
        """Initialize the persistent SQLite3 database connection and table schema.

        Args:
            db_path: Path to the SQLite3 database file, or ':memory:' for transient storage.
        """
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Create the memories table schema if it does not already exist."""
        with self._conn:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    embedding TEXT,
                    timestamp REAL NOT NULL,
                    metadata TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_session ON memories(session_id)"
            )

    def _generate_embedding(
        self, text: str, client: Optional[Any] = None, model: str = "text-embedding-3-small"
    ) -> Optional[List[float]]:
        """Generate a dense vector embedding using OpenAI API if client is available.

        Args:
            text: String content to embed.
            client: Optional OpenAI client instance.
            model: Embedding model identifier.

        Returns:
            List of floats representing the embedding vector, or None if client unavailable.
        """
        if client is None or not text.strip():
            return None

        try:
            response = client.embeddings.create(
                input=text,
                model=model,
            )
            return response.data[0].embedding
        except Exception as exc:
            import logging
            logging.getLogger("agent_memory").warning(
                f"Embedding generation failed, falling back to lexical search. Error: {exc}"
            )
            return None

    def save_information(
        self,
        session_id: str,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
        client: Optional[Any] = None,
    ) -> None:
        """Append and persist a tagged memory entry into SQLite3 with optional embeddings.

        Args:
            session_id: Unique identifier for the execution session.
            key: Semantic descriptor tag for the memory (e.g., 'preference_rules').
            value: The content or object to be stored.
            metadata: Optional additional contextual attributes.
            client: Optional OpenAI client for generating semantic embeddings.
        """
        if not session_id or not isinstance(session_id, str):
            raise ValueError("session_id must be a non-empty string.")
        if not key or not isinstance(key, str):
            raise ValueError("key must be a non-empty string.")

        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        text_for_embedding = f"{key}: {val_str}"

        # Generate dense embedding vector if client is supplied
        embedding_vec = self._generate_embedding(text_for_embedding, client=client)
        embedding_json = json.dumps(embedding_vec) if embedding_vec else None
        meta_json = json.dumps(metadata or {})
        now = time.time()

        with self._conn:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO memories (session_id, key, value, embedding, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, key, val_str, embedding_json, now, meta_json),
            )

    def recall_relevant_context(
        self,
        session_id: str,
        query: str,
        top_k: int = 3,
        similarity_threshold: float = 0.1,
        client: Optional[Any] = None,
        semantic_weight: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant memory entries using Hybrid (Semantic + Lexical) ranking.

        Computes:
        - Lexical similarity via `difflib.SequenceMatcher`
        - Semantic similarity via cosine distance of dense vectors (when client is available)
        - Blended Hybrid Score = (semantic_weight * semantic_score) + ((1 - semantic_weight) * lexical_score)

        Args:
            session_id: The session ID to search within.
            query: The search term or preference topic.
            top_k: Maximum number of ranked records to return.
            similarity_threshold: Minimum match score threshold.
            client: Optional OpenAI client for query embedding.
            semantic_weight: Weight allocated to semantic cosine vs lexical [0.0 to 1.0].

        Returns:
            A list of dictionary records sorted by descending relevance.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT key, value, embedding, timestamp, metadata FROM memories WHERE session_id = ?",
            (session_id,),
        )
        rows = cursor.fetchall()

        if not rows:
            return []

        query_lower = query.lower().strip()
        query_embedding = self._generate_embedding(query, client=client)

        scored_records: List[Tuple[float, Dict[str, Any]]] = []

        for row in rows:
            key_str = row["key"]
            val_str = row["value"]
            meta_dict = json.loads(row["metadata"]) if row["metadata"] else {}
            emb_raw = row["embedding"]
            doc_embedding = json.loads(emb_raw) if emb_raw else None

            # 1. Lexical Score Calculation
            key_ratio = difflib.SequenceMatcher(None, query_lower, key_str.lower()).ratio()
            val_ratio = difflib.SequenceMatcher(None, query_lower, val_str.lower()).ratio()

            if query_lower in key_str.lower() or any(part in key_str.lower() for part in query_lower.split()):
                key_ratio = max(key_ratio, 0.75)
            if query_lower in val_str.lower():
                val_ratio = max(val_ratio, 0.6)

            lexical_score = max(key_ratio, val_ratio * 0.8)

            # 2. Semantic Score Calculation
            semantic_score = 0.0
            if query_embedding and doc_embedding:
                semantic_score = max(0.0, _cosine_similarity(query_embedding, doc_embedding))

            # 3. Hybrid Blend
            if query_embedding and doc_embedding:
                final_score = (semantic_weight * semantic_score) + ((1.0 - semantic_weight) * lexical_score)
            else:
                final_score = lexical_score

            if final_score >= similarity_threshold:
                record = {
                    "key": key_str,
                    "value": val_str,
                    "timestamp": row["timestamp"],
                    "metadata": meta_dict,
                    "score": round(final_score, 4),
                }
                scored_records.append((final_score, record))

        # Sort descending by final score
        scored_records.sort(key=lambda x: x[0], reverse=True)

        return [item[1] for item in scored_records[:top_k]]

    def clear_session(self, session_id: str) -> None:
        """Purge all stored memory records for an active session.

        Args:
            session_id: The session ID whose history will be deleted.
        """
        with self._conn:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM memories WHERE session_id = ?", (session_id,))

    def list_all_sessions(self) -> List[str]:
        """List all unique session identifiers currently stored."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT DISTINCT session_id FROM memories")
        return [row[0] for row in cursor.fetchall()]

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        try:
            self._conn.close()
        except Exception:
            pass


def format_memory_for_prompt(memories: List[Dict[str, Any]]) -> str:
    """Format recalled memory entries into an injectable system prompt section.

    Args:
        memories: List of memory dictionary records from `recall_relevant_context`.

    Returns:
        A structured string block suitable for appending to the agent system prompt.
    """
    if not memories:
        return ""

    lines: List[str] = [
        "\n--- RECALLED CONTEXT & PREFERENCES (FROM PREVIOUS SESSIONS) ---"
    ]
    for idx, mem in enumerate(memories, 1):
        key = mem.get("key", "Context")
        val = mem.get("value", "")
        lines.append(f"[{idx}] {key}: {val}")

    lines.append("Please adhere strictly to these learned preferences and instructions.")
    lines.append("----------------------------------------------------------------\n")
    return "\n".join(lines)
