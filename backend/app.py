from __future__ import annotations

import csv
import secrets
import io
import json
import logging
import math
import os
import pickle
import re
import sqlite3
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from contextlib import asynccontextmanager, closing
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
import networkx as nx
import yaml
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
DB_PATH = Path(os.getenv("PROGRESSSYNC_DB", ROOT / "data" / "progresssync.db"))
TERM_PATH = ROOT / "data" / "terminology_map.v1.yaml"
FRONTEND = ROOT / "frontend-react" / "dist"  # the built React UI; FastAPI serves it at /
DISCIPLINES = {"civil", "piping", "static_equipment", "rotating_equipment", "electrical", "instrumentation", "hse"}
SEMANTIC_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SEMANTIC_MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"  # pinned; provision with scripts/provision_model.py
SEMANTIC_MODEL_PATH = Path(os.getenv("PROGRESSSYNC_MODEL_PATH", ROOT / "ml_artifacts" / "semantic_model"))
_semantic_model = None
_activity_embeddings = {}
_event_embeddings = {}

RERANKER_MODEL_PATH = ROOT / "ml_artifacts" / "reranker_v0.1.pkl"
RERANKER_ENABLED = os.getenv("PROGRESSSYNC_USE_RERANKER", "false").lower() in {"1", "true", "yes", "on"}
RERANKER_AUTO_THRESHOLD = 0.90
RERANKER_REVIEW_THRESHOLD = 0.50
RERANKER_MARGIN_THRESHOLD = 0.10
_reranker_artifact = None


def get_reranker():
    """Load the trained reranker lazily when explicitly enabled."""
    global _reranker_artifact

    if not RERANKER_ENABLED:
        return None

    if _reranker_artifact is None:
        if not RERANKER_MODEL_PATH.exists():
            return None

        with RERANKER_MODEL_PATH.open("rb") as handle:
            _reranker_artifact = pickle.load(handle)

    return _reranker_artifact


def get_reranker_feature_values(
    event: dict[str, Any],
    activity: Any,
    scores: dict[str, float],
    baseline_rank: int,
    top_score: float,
    second_score: float,
) -> dict[str, float]:
    """Build exactly the feature schema used by train_reranker.py."""
    identifiers = event.get("identifiers") or []

    identifier_match = int(
        any(
            id_in(identifier, norm(activity["activity_code"]))
            or id_in(identifier, norm(activity["description"]))
            for identifier in identifiers
        )
    )

    discipline_match = int(
        bool(event.get("discipline"))
        and event["discipline"] == activity["discipline"]
    )

    location_match = int(
        bool(event.get("location_terms"))
        and norm(event["location_terms"]) == norm(activity["location"])
    )

    return {
        "score_id": scores["score_id"],
        "score_lexical": scores["score_lexical"],
        "score_semantic": scores["score_semantic"],
        "score_context": scores["score_context"],
        "temporal_factor": scores["temporal_factor"],
        "fused_score": scores["fused_score"],
        "baseline_rank": float(baseline_rank),
        "gap_from_top": top_score - scores["fused_score"],
        "top_score": top_score,
        "second_score": second_score,
        "margin": top_score - second_score,
        "identifier_match": float(identifier_match),
        "discipline_match": float(discipline_match),
        "location_match": float(location_match),
    }


def get_explicit_unknown_signal(event: dict[str, Any]) -> bool:
    """Detect explicit field language saying the package/activity is unknown."""
    text = norm(event.get("source_text", ""))
    if re.search(r"\bzz[- ]?\d{2,4}\b", text, re.I):
        return True
    return "unknown work package" in text or "unknown package" in text


def get_semantic_model():
    global _semantic_model

    if _semantic_model is None:
        try:
            from sentence_transformers import SentenceTransformer

            model_source = str(SEMANTIC_MODEL_PATH) if SEMANTIC_MODEL_PATH.exists() else SEMANTIC_MODEL_NAME
            revision = None if SEMANTIC_MODEL_PATH.exists() else SEMANTIC_MODEL_REVISION
            if SEMANTIC_MODEL_PATH.exists():
                _semantic_model = SentenceTransformer(model_source)
            else:
                _semantic_model = SentenceTransformer(model_source, revision=revision, local_files_only=True)
        except Exception as exc:
            LOGGER.exception("Failed to load semantic model %s from %s", SEMANTIC_MODEL_NAME, SEMANTIC_MODEL_PATH)
            raise SemanticModelMissing(
                f"Semantic model {SEMANTIC_MODEL_NAME}@{SEMANTIC_MODEL_REVISION[:12]} is not provisioned at {SEMANTIC_MODEL_PATH}. "
                f"Model load error: {type(exc).__name__}: {exc}. Run once with network access: python scripts/provision_model.py"
            ) from exc

    return _semantic_model


class SemanticModelMissing(RuntimeError):
    pass


def semantic_similarity(event_text: str, activity_text: str) -> float:
    model = get_semantic_model()

    event_key = norm(event_text)
    activity_key = norm(activity_text)

    if event_key not in _event_embeddings:
        _event_embeddings[event_key] = model.encode(
            event_key,
            normalize_embeddings=True,
        )

    if activity_key not in _activity_embeddings:
        _activity_embeddings[activity_key] = model.encode(
            activity_key,
            normalize_embeddings=True,
        )

    return float(_event_embeddings[event_key] @ _activity_embeddings[activity_key])
SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activities (
 id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, activity_code TEXT NOT NULL, description TEXT NOT NULL,
 wbs_path TEXT, level INTEGER NOT NULL, discipline TEXT NOT NULL, location TEXT, planned_start TEXT,
 planned_finish TEXT, planned_duration REAL, actual_start TEXT, actual_finish TEXT, percent_complete REAL DEFAULT 0,
 status TEXT DEFAULT 'not_started', contractor TEXT, resource TEXT, embedding TEXT DEFAULT '[]', at_risk INTEGER DEFAULT 0, at_risk_reason TEXT,
 UNIQUE(project_id, activity_code)
);
CREATE TABLE IF NOT EXISTS activity_dependencies (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, predecessor_id INTEGER NOT NULL, successor_id INTEGER NOT NULL, dependency_type TEXT DEFAULT 'FS', lag REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS cpm_state (activity_id INTEGER PRIMARY KEY, early_start TEXT, early_finish TEXT, late_start TEXT, late_finish TEXT, total_float REAL, critical INTEGER, project_finish TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS schedule_snapshots (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, reason TEXT, created_at TEXT NOT NULL, project_finish TEXT, state_json TEXT NOT NULL, data_date TEXT);
CREATE TABLE IF NOT EXISTS field_reports (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, source TEXT NOT NULL, raw_text TEXT NOT NULL, submitted_at TEXT NOT NULL, latency_ms REAL, status TEXT DEFAULT 'received');
CREATE TABLE IF NOT EXISTS execution_events (id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL, event_type TEXT, discipline TEXT, activity_terms TEXT, identifiers TEXT, location_terms TEXT, quantity REAL, unit TEXT, progress REAL, event_timestamp TEXT, source_text TEXT, source_span TEXT, extraction_confidence REAL, status TEXT DEFAULT 'PENDING');
CREATE TABLE IF NOT EXISTS match_candidates (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, activity_id INTEGER NOT NULL, score_id REAL, score_lexical REAL, score_semantic REAL, score_context REAL, temporal_factor REAL, fused_score REAL, rank INTEGER, evidence_json TEXT);
CREATE TABLE IF NOT EXISTS match_decisions (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, decision TEXT NOT NULL, activity_id INTEGER, top_score REAL, second_score REAL, margin REAL, actor TEXT, comment TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS terminology_map (id INTEGER PRIMARY KEY, field_term TEXT, canonical_term TEXT, discipline TEXT, version TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS delay_causes (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, cause TEXT, notes TEXT, project_id INTEGER, activity_id INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS execution_memory (
 activity_id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, activity_code TEXT, activity_type TEXT, discipline TEXT, location TEXT,
 planned_start TEXT, planned_finish TEXT, planned_duration REAL, actual_start TEXT, actual_finish TEXT, actual_duration REAL,
 start_variance REAL, finish_variance REAL, duration_variance REAL, delay_cause TEXT, notes TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_sessions (id TEXT PRIMARY KEY, project_id INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'idle', event_id INTEGER, selected_activity_id INTEGER, rounds INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_messages (id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, event_id INTEGER, created_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_approval_per_event ON match_decisions(event_id) WHERE decision='APPROVED';
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, activity_id INTEGER, event_id INTEGER, old_value TEXT, new_value TEXT, source TEXT, evidence TEXT, score REAL, actor TEXT, approval_status TEXT, created_at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


ADDED_COLUMNS = {
    "activities": {"at_risk_reason": "TEXT"},
    "delay_causes": {"project_id": "INTEGER", "activity_id": "INTEGER", "created_at": "TEXT"},
    "schedule_snapshots": {"data_date": "TEXT"},
    "field_reports": {"client_report_id": "TEXT", "response_json": "TEXT"},
}


def init_db() -> None:
    with closing(connect()) as db:
        db.executescript(SCHEMA)
        # Additive migration for databases created before a column existed.
        for table, columns in ADDED_COLUMNS.items():
            present = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            for column, kind in columns.items():
                if column not in present:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS field_reports_client_ref ON field_reports(project_id, client_report_id) WHERE client_report_id IS NOT NULL")
        load_terms(db)
        db.commit()
        if not db.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
            db.execute("INSERT INTO projects(name, created_at) VALUES (?, ?)", ("OIL Demo Project", now()))
            seed_schedule(db)
            recompute(db, 1, "initial baseline")
        for (project_id,) in db.execute("SELECT id FROM projects").fetchall():
            refresh_if_stale(db, project_id)


def refresh_if_stale(db: sqlite3.Connection, project_id: int) -> None:
    """Recompute the forecast CPM / at-risk flags when the data date (today) has moved since the
    latest snapshot (audit F-05), so a GET never shows yesterday's forecast."""
    latest = db.execute("SELECT data_date FROM schedule_snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    if latest and latest["data_date"] == date.today().isoformat():
        return
    if not db.execute("SELECT 1 FROM activities WHERE project_id=? LIMIT 1", (project_id,)).fetchone():
        return
    try:
        recompute(db, project_id, "data date changed")
    except ScheduleCycle:
        pass  # a cyclic graph cannot be forecast; explicit recompute/import report the 409


def load_terms(db: sqlite3.Connection, path: Path | None = None) -> None:
    """Sync terminology_map from the YAML file, which is the only source of truth."""
    path = path or TERM_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows, seen = [], set()
    for number, item in enumerate(document.get("mappings") or [], 1):
        field_term, canonical = str(item.get("field_term") or "").strip(), str(item.get("canonical_term") or "").strip()
        discipline = item.get("discipline")
        if not field_term or not canonical or discipline not in DISCIPLINES:
            raise ValueError(f"{path.name}: mapping {number} needs field_term, canonical_term and a valid discipline")
        if norm(field_term) in seen:
            raise ValueError(f"{path.name}: duplicate field_term '{field_term}' (after normalization)")
        seen.add(norm(field_term))
        rows.append((field_term, canonical, discipline, str(document.get("version", "")), f"{path.name}: {document.get('source', '')}"))
    db.execute("DELETE FROM terminology_map")
    db.executemany("INSERT INTO terminology_map(field_term, canonical_term, discipline, version, source) VALUES (?, ?, ?, ?, ?)", rows)


def seed_schedule(db: sqlite3.Connection) -> None:
    rows = []
    base = date.today() - timedelta(days=3)
    templates = [
        ("CIV", "Foundation and concrete works", "civil", "Area A"),
        ("PIP", "Erect line XX102 spool", "piping", "R03"),
        ("STA", "Erect vessel V-201", "static_equipment", "Unit 2"),
        ("ROT", "Install pump CT-103", "rotating_equipment", "Unit 2"),
        ("ELE", "Install cable tray", "electrical", "R03"),
        ("INS", "Calibrate pressure transmitter", "instrumentation", "Unit 2"),
        ("HSE", "Permit and safety inspection", "hse", "Site"),
    ]
    # Five packages of seven disciplines. Within a package: civil -> piping/static/electrical,
    # static -> rotating, electrical -> instrumentation, everything -> HSE close-out.
    # Civil and piping crews also roll package to package. Planned dates follow these FS links.
    within = [(0, 1), (0, 2), (2, 3), (0, 4), (4, 5), (1, 6), (3, 6), (5, 6)]
    links = [(7 * p + a, 7 * p + b) for p in range(5) for a, b in within]
    links += [(7 * p + k, 7 * (p + 1) + k) for p in range(4) for k in (0, 1)]
    finish_day: dict[int, int] = {}
    for i in range(35):
        prefix, desc, discipline, location = templates[i % len(templates)]
        code = f"{prefix}-L5-{i+1:03d}"
        if discipline == "piping":
            desc = f"Erect line XX{102 + i // 7:03d} spool"
        duration = 3 + i % 4
        start_day = max((finish_day[a] for a, b in links if b == i), default=0)
        finish_day[i] = start_day + duration
        start = base + timedelta(days=start_day)
        finish = start + timedelta(days=duration - 1)
        rows.append((1, code, f"{desc} {i+1:03d}", f"{discipline.upper()} / {location} / PACKAGE {i//7+1}", 5 if i % 4 else 6, discipline, location, start.isoformat(), finish.isoformat(), duration, 0, "not_started"))
    db.executemany("INSERT INTO activities(project_id,activity_code,description,wbs_path,level,discipline,location,planned_start,planned_finish,planned_duration,percent_complete,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    ids = [row[0] for row in db.execute("SELECT id FROM activities WHERE project_id=1 ORDER BY id")]
    db.executemany("INSERT INTO activity_dependencies(project_id,predecessor_id,successor_id,dependency_type,lag) VALUES (1,?,?,'FS',0)", [(ids[a], ids[b]) for a, b in links])
    # Demo history: the first foundation finished one day late (today instead of yesterday).
    db.execute("UPDATE activities SET actual_start=?, actual_finish=?, percent_complete=100, status='complete' WHERE id=?", (base.isoformat(), date.today().isoformat(), ids[0]))
    upsert_memory(db, ids[0])


def parse_day(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):  # XLSX cells arrive as datetime
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    # OCR fix only inside identifiers: an 'o' touching a digit (XX1O2, RO3) is a zero.
    # Ordinary words (spool, foundation, completed) must stay intact.
    text = re.sub(r"(?<=\d)o|o(?=\d)", "0", text)
    text = re.sub(r"([a-z])([0-9])", r"\1 \2", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return set(norm(text).split())


# Completion/start inference with a negation and future-tense guard (audit F-01).
# A guarded phrase blocks the verb it governs: "not completed yet", "will be completed tomorrow",
# "has not started", "isn't finished", "yet to complete", "completion is pending", "will start tomorrow".
COMPLETION_WORDS = re.compile(r"\b(?:complete|completed|finished)\b")
START_WORDS = re.compile(r"\bstart(?:s|ed|ing)?\b")
NEGATED_OR_FUTURE = re.compile(
    r"\b(?:not|never|no|yet to|pending|will|shall|going to|to be|scheduled to|planned to|expected to|about to|\w+n t)"
    r"(?:\s+(?:be|been|being|yet|fully|get|got|have|has|had))*"
    r"\s+(?:complet|finish|start|begin|began|commenc)\w*"
    r"|\b(?:complet|finish|start|begin|commenc)\w*\s+(?:(?:is|was|are|still|yet)\s+)*(?:pending|awaited|tomorrow|later)\b"
)


LINE_REF = re.compile(r"\b(?:line|ln|l)(?:\s*no\.?)?\s*[-#:.]?\s*(\d{3,5})\b", re.I)
TAG_REF = re.compile(r"\b(?:[A-Z]{2,5}[- ]?\d{2,4}|[A-Z]{1,3}\d{3,4}|[A-Z][- ]\d{3,4})\b(?!\s*%)")


def id_in(identifier: str, normalized_text: str) -> bool:
    """Whole-token match: "p 301" is in "install pump p 301" but "210" is not in "line 2105"."""
    nid = norm(identifier)
    return bool(nid) and f" {nid} " in f" {normalized_text} "


def unguarded(pattern: re.Pattern[str], normalized: str) -> bool:
    """True if some occurrence of pattern is not inside a negated/future-tense phrase."""
    blocked = [m.span() for m in NEGATED_OR_FUTURE.finditer(normalized)]
    return any(not any(a <= m.start() < b for a, b in blocked) for m in pattern.finditer(normalized))


def started_signal(text: str) -> bool:
    return unguarded(START_WORDS, norm(text))


def extract_event(text: str, source: str, report_id: int, event_date: date | None = None) -> dict[str, Any]:
    clean = text.strip()
    normalized = norm(clean)

    # Detect discipline from field language.
    discipline = next(
        (
            d
            for d in DISCIPLINES
            if d.replace("_", " ") in normalized
            or d.split("_")[0] in normalized
        ),
        None,
    )

    if (
        "pipe" in normalized
        or "spool" in normalized
        or "hydro" in normalized
        or ("line" in normalized and "erect" in normalized)
    ):
        discipline = "piping"
    elif "pump" in normalized or "rotating" in normalized:
        discipline = "rotating_equipment"
    elif "vessel" in normalized or "static" in normalized:
        discipline = "static_equipment"
    elif "cable" in normalized or "electrical" in normalized:
        discipline = "electrical"
    elif "transmitter" in normalized or "instrument" in normalized:
        discipline = "instrumentation"
    elif (
        "safety" in normalized
        or "permit" in normalized
        or "inspection" in normalized
    ):
        discipline = "hse"
    elif "foundation" in normalized or "concrete" in normalized:
        discipline = "civil"

    # Detect rack-style locations such as R03 / rack 3.
    location = None
    rack = re.search(r"\b(?:rack|r)[ -]?(\d+)\b", clean, re.I)
    if rack:
        location = f"R{int(rack.group(1)):02d}"

    # Detect equipment/activity identifiers (audit F-04). A bare number only counts with line
    # context ("Line 2104", "Ln 2111", "L-2104", "Line No. 2104"); tags include single-letter
    # forms ("P-301", "P 301", "V-201"). "A 100%" is a percentage, not a tag.
    line_ids = [m.group(1) for m in LINE_REF.finditer(clean)]
    equipment = list(dict.fromkeys(TAG_REF.findall(LINE_REF.sub(" ", clean)) + line_ids))

    # Detect progress percentage.
    progress_match = re.search(r"(\d{1,3})\s*%", clean)

    # Detect quantities.
    quantity_match = re.search(
        r"(?:qty|quantity|installed|completed)\s*[:=]?\s*"
        r"(\d+(?:\.\d+)?)\s*(m|meter|meters|mm|inch|in|ea|each)?",
        clean,
        re.I,
    )

    # Detect time.
    time_match = re.search(
        r"(?:at|@)\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        clean,
        re.I,
    )

    activity_terms = clean
    span = [0, len(clean)]
    event_timestamp = (event_date or date.today()).isoformat()

    guarded = bool(NEGATED_OR_FUTURE.search(normalized))
    completed_word = unguarded(COMPLETION_WORDS, normalized)
    progress = float(progress_match.group(1)) if progress_match else (100.0 if completed_word else None)
    if progress is not None and progress >= 100 and guarded and not completed_word:
        progress = None  # "will be completed tomorrow, 100%" contradicts itself: let a planner decide
    inference_note = (
        "negated or future-tense wording: no completion or start was inferred"
        if guarded and progress is None and not started_signal(clean) else None
    )

    return {
        "report_id": report_id,
        "event_type": "progress_update",
        "discipline": discipline,
        "activity_terms": activity_terms,
        "identifiers": equipment,
        "line_numbers": line_ids,
        "location_terms": location,
        "quantity": float(quantity_match.group(1)) if quantity_match else None,
        "unit": quantity_match.group(2) if quantity_match else None,
        "progress": progress,
        "inference_note": inference_note,
        "event_timestamp": event_timestamp,
        "source_text": clean,
        "source_span": span,
        "extraction_confidence": 0.86 if discipline else 0.62,
        "time_text": time_match.group(1) if time_match else None,
    }


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def score_candidate(
    event: dict[str, Any],
    activity: sqlite3.Row,
    terms: list[sqlite3.Row],
) -> tuple[dict[str, float], dict[str, Any]]:
    field = norm(event["activity_terms"])
    description = norm(activity["description"])
    activity_code = norm(activity["activity_code"])

    # 1. Identifier / activity-code score.
    score_id = 0.0
    # Equipment tags identify one activity (1.0, and they floor lexical/semantic below). A line
    # number is shared by every activity on that line (erect, test, bolt), so it is line-level
    # evidence only: 0.82, the same level as an identifier-like activity-code part.
    line_numbers = event.get("line_numbers") or []
    if any(
        id_in(identifier, activity_code) or id_in(identifier, description)
        for identifier in event["identifiers"] if identifier not in line_numbers
    ):
        score_id = 1.0
    elif any(id_in(number, activity_code) or id_in(number, description) for number in line_numbers):
        score_id = 0.82
    elif any(
        # Whole-token match on identifier-like code parts ("2104" in "PIP-2104"); a bare prefix such
        # as "pip" must not match inside "piping" (audit B-14).
        part in field.split()
        for part in activity_code.split()
        if len(part) > 2 and any(ch.isdigit() for ch in part)
    ):
        score_id = 0.82

    # 2. Field terminology mapping.
    mapped = []
    mapped_field = field
    for term in terms:
        # Terms go through the same norm() as the field text (e.g. "CT103" -> "ct 103").
        field_term = norm(term["field_term"])
        if field_term and field_term in mapped_field:
            mapped.append(dict(term))
            mapped_field = mapped_field.replace(
                field_term,
                norm(term["canonical_term"]),
            )

    # 3. Lexical score.
    overlap = (
        len(tokens(mapped_field) & tokens(description))
        / max(1, len(tokens(description)))
    )
    score_lexical = max(
        similarity(mapped_field, description),
        similarity(field, description),
        overlap,
    )
    if score_id >= 1.0:
        score_lexical = max(score_lexical, 0.9)

    # 4. Real MiniLM semantic similarity.
    score_semantic = semantic_similarity(
        mapped_field,
        description,
    )
    if score_id >= 1.0:
        score_semantic = max(score_semantic, 0.92)

    # 5. Context score.
    context = 0.0
    if (
        event.get("discipline")
        and event["discipline"] == activity["discipline"]
    ):
        context += 0.6
    elif (
        event.get("discipline")
        and event["discipline"] != activity["discipline"]
    ):
        context -= 0.35

    if (
        event.get("location_terms")
        and norm(event["location_terms"]) == norm(activity["location"])
    ):
        context += 0.4

    score_context = max(0.0, min(1.0, 0.5 + context))

    # 6. Temporal compatibility.
    temporal_factor = 1.0
    event_day = parse_day(event.get("event_timestamp"))
    start = parse_day(activity["planned_start"])
    finish = parse_day(activity["planned_finish"])

    if event_day and start and finish:
        if start <= event_day <= finish:
            temporal_factor = 1.0
        elif event_day < start:
            temporal_factor = 0.94
        else:
            temporal_factor = 0.9

    # 7. Existing fusion formula, now using real semantic similarity.
    base = (
        0.30 * score_id
        + 0.15 * score_lexical
        + 0.25 * score_semantic
        + 0.30 * score_context
    )

    evidence = {
        "activity_code": activity["activity_code"],
        "description": activity["description"],
        "mapped_terms": mapped,
        "source_span": event["source_span"],
        "semantic_model": SEMANTIC_MODEL_NAME,
    }

    return {
        "score_id": score_id,
        "score_lexical": score_lexical,
        "score_semantic": score_semantic,
        "score_context": score_context,
        "temporal_factor": temporal_factor,
        "fused_score": base * temporal_factor,
    }, evidence


COMPLETED_ACTIVITY_FACTOR = 0.85  # same kind of multiplier as the temporal factor; thresholds unchanged


def make_match(db: sqlite3.Connection, project_id: int, event_id: int, event: dict[str, Any]) -> dict[str, Any]:
    activities = db.execute(
        "SELECT * FROM activities WHERE project_id=? ORDER BY id", (project_id,)
    ).fetchall()
    terms = db.execute("SELECT * FROM terminology_map").fetchall()

    candidates = []

    for activity in activities:
        if (
            event.get("discipline")
            and event["discipline"] != activity["discipline"]
            and event.get("extraction_confidence", 0) >= 0.8
        ):
            continue

        scores, evidence = score_candidate(
            event,
            activity,
            terms,
        )

        # A finished activity is an unlikely target for a report of fresh work (audit F-13):
        # flag it, and down-rank it unless the report itself is a completion report.
        if activity["status"] == "complete" or activity["actual_finish"]:
            evidence["completed_activity"] = True
            if event.get("progress") is None or event["progress"] < 100:
                scores["fused_score"] *= COMPLETED_ACTIVITY_FACTOR
                evidence["status_factor"] = COMPLETED_ACTIVITY_FACTOR

        candidates.append({
            "scores": scores,
            "evidence": evidence,
            "activity": activity,
        })

    if not candidates:
        # Nothing in this project can be scored: preserve the observation as UNMATCHED.
        db.execute(
            "INSERT INTO match_decisions(event_id,decision,activity_id,top_score,second_score,margin,actor,comment,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (event_id, "UNMATCHED", None, 0.0, 0.0, 0.0, "system", "no candidate activities in project", now()),
        )
        db.execute("UPDATE execution_events SET status='UNMATCHED' WHERE id=?", (event_id,))
        db.commit()
        return {
            "decision": "UNMATCHED", "top_score": 0.0, "second_score": 0.0, "margin": 0.0, "activity_id": None,
            "baseline_top_score": 0.0, "baseline_second_score": 0.0, "baseline_margin": 0.0,
            "reranker_enabled": RERANKER_ENABLED, "reranker_used": False, "reranker_version": None,
        }

    # First rank using the existing deterministic + MiniLM fusion score.
    candidates.sort(
        key=lambda item: item["scores"]["fused_score"],
        reverse=True,
    )

    baseline_top = candidates[0]["scores"]["fused_score"]
    baseline_second = (
        candidates[1]["scores"]["fused_score"]
        if len(candidates) > 1
        else 0.0
    )
    baseline_margin = baseline_top - baseline_second

    # Optional learned reranking layer. It is explicitly opt-in so the
    # existing production/demo behavior remains unchanged until validated.
    reranker = get_reranker()
    reranker_used = False
    reranker_version = None

    if reranker:
        feature_names = reranker.get("features", [])
        model = reranker.get("model")
        reranked = []

        for rank, candidate in enumerate(candidates[:20], start=1):
            values = get_reranker_feature_values(
                event=event,
                activity=candidate["activity"],
                scores=candidate["scores"],
                baseline_rank=rank,
                top_score=baseline_top,
                second_score=baseline_second,
            )

            vector = [values[name] for name in feature_names]
            probability = float(model.predict_proba([vector])[0][1])

            candidate["reranker_probability"] = probability
            candidate["baseline_rank"] = rank
            candidate["evidence"]["reranker_probability"] = probability
            candidate["evidence"]["baseline_rank"] = rank

            reranked.append(candidate)

        reranked.sort(
            key=lambda item: item["reranker_probability"],
            reverse=True,
        )

        candidates[:20] = reranked
        reranker_used = True
        reranker_version = reranker.get("version", "unknown")

    # Persist the best 20 candidates. `rank` is the final rank shown to the UI.
    for rank, candidate in enumerate(candidates[:20], start=1):
        scores = candidate["scores"]
        evidence = candidate["evidence"]
        activity = candidate["activity"]

        evidence["matching_stage"] = (
            "learned_reranker" if reranker_used else "fusion_only"
        )
        if reranker_used:
            evidence["reranker_version"] = reranker_version

        db.execute(
            "INSERT INTO match_candidates("
            "event_id,activity_id,score_id,score_lexical,score_semantic,"
            "score_context,temporal_factor,fused_score,rank,evidence_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                activity["id"],
                scores["score_id"],
                scores["score_lexical"],
                scores["score_semantic"],
                scores["score_context"],
                scores["temporal_factor"],
                scores["fused_score"],
                rank,
                json.dumps(evidence),
            ),
        )

    top_candidate = candidates[0]
    second_candidate = candidates[1] if len(candidates) > 1 else None

    top_activity_id = top_candidate["activity"]["id"]
    top_fused_score = top_candidate["scores"]["fused_score"]
    second_fused_score = (
        second_candidate["scores"]["fused_score"]
        if second_candidate
        else 0.0
    )
    fused_margin = top_fused_score - second_fused_score

    explicit_unknown = get_explicit_unknown_signal(event)

    if reranker_used:
        top_probability = top_candidate["reranker_probability"]
        second_probability = (
            second_candidate["reranker_probability"]
            if second_candidate
            else 0.0
        )
        reranker_margin = top_probability - second_probability

        if explicit_unknown:
            decision = "UNMATCHED"
        elif (
            top_probability >= RERANKER_AUTO_THRESHOLD
            and reranker_margin >= RERANKER_MARGIN_THRESHOLD
        ):
            decision = "AUTO_MATCHED"
        elif top_probability >= RERANKER_REVIEW_THRESHOLD:
            decision = "REVIEW_REQUIRED"
        else:
            decision = "UNMATCHED"

        top_score_for_decision = top_probability
        second_score_for_decision = second_probability
        margin_for_decision = reranker_margin
    else:
        decision = (
            "AUTO_MATCHED"
            if top_fused_score >= 0.82 and fused_margin >= 0.12
            else "REVIEW_REQUIRED"
            if top_fused_score >= 0.45
            else "UNMATCHED"
        )

        if explicit_unknown:
            decision = "UNMATCHED"

        top_score_for_decision = top_fused_score
        second_score_for_decision = second_fused_score
        margin_for_decision = fused_margin

    # A confident match with nothing to apply (no progress, no start, e.g. "not completed yet")
    # must not be offered as a one-click update: the planner reviews it instead.
    nothing_to_apply = event.get("progress") is None and not started_signal(event.get("source_text", ""))
    downgraded = decision == "AUTO_MATCHED" and nothing_to_apply
    if downgraded:
        decision = "REVIEW_REQUIRED"

    auto_t, review_t, margin_t = (RERANKER_AUTO_THRESHOLD, RERANKER_REVIEW_THRESHOLD, RERANKER_MARGIN_THRESHOLD) if reranker_used else (0.82, 0.45, 0.12)
    top_s, margin_s = top_score_for_decision, margin_for_decision
    if explicit_unknown:
        reason = "report explicitly names an unknown work package"
    elif downgraded:
        reason = f"confident match (score {top_s:.3f}) but the report states no progress or start to apply" + (
            " — its wording is negated or future tense" if event.get("inference_note") else "")
    elif decision == "AUTO_MATCHED":
        reason = f"top score {top_s:.3f} >= {auto_t} and margin {margin_s:.3f} >= {margin_t}"
    elif decision == "REVIEW_REQUIRED":
        reason = f"top score {top_s:.3f} below {auto_t}" if top_s < auto_t else f"margin {margin_s:.3f} to runner-up below {margin_t}"
    else:
        reason = f"top score {top_s:.3f} below the {review_t} review threshold"

    activity_id = (
        top_activity_id
        if decision != "UNMATCHED"
        else None
    )

    db.execute(
        "INSERT INTO match_decisions("
        "event_id,decision,activity_id,top_score,second_score,margin,actor,comment,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            event_id,
            decision,
            activity_id,
            top_score_for_decision,
            second_score_for_decision,
            margin_for_decision,
            "system",
            reason,
            now(),
        ),
    )

    db.execute(
        "UPDATE execution_events SET status=? WHERE id=?",
        (decision, event_id),
    )
    db.commit()

    return {
        "decision": decision,
        "reason": reason,
        "top_score": top_score_for_decision,
        "second_score": second_score_for_decision,
        "margin": margin_for_decision,
        "activity_id": activity_id,
        "baseline_top_score": top_fused_score,
        "baseline_second_score": second_fused_score,
        "baseline_margin": fused_margin,
        "reranker_enabled": RERANKER_ENABLED,
        "reranker_used": reranker_used,
        "reranker_version": reranker_version,
    }


def cpm_state(db: sqlite3.Connection, project_id: int, data_date: date | None = None) -> dict[int, dict[str, Any]]:
    acts = db.execute("SELECT * FROM activities WHERE project_id=?", (project_id,)).fetchall()
    edges = db.execute("SELECT predecessor_id, successor_id, dependency_type, lag FROM activity_dependencies WHERE project_id=?", (project_id,)).fetchall()
    graph = nx.DiGraph()
    graph.add_nodes_from(a["id"] for a in acts)
    graph.add_edges_from((e["predecessor_id"], e["successor_id"], {"type": (e["dependency_type"] or "FS").upper(), "lag": float(e["lag"] or 0)}) for e in edges)
    by_id = {a["id"]: a for a in acts}
    if not nx.is_directed_acyclic_graph(graph):
        cycle = [by_id[u]["activity_code"] if u in by_id else str(u) for u, _ in nx.find_cycle(graph)]
        raise ScheduleCycle("Dependency graph contains a cycle: " + " -> ".join(cycle + cycle[:1]))

    # Day offsets are measured from the earliest planned start. With a data date (today), CPM is a
    # forecast: actual dates fix completed work, in-progress work keeps its remaining duration, and
    # unstarted work cannot start before the data date. Without one, it is the pure planned network.
    starts = [d for d in (parse_day(a["planned_start"]) for a in acts) if d]
    origin = min(starts) if starts else (data_date or date.today())
    dd = (data_date - origin).days if data_date else None

    def offset(value: Any) -> int | None:
        day = parse_day(value)
        return (day - origin).days if day else None

    es: dict[int, float] = {}
    ef: dict[int, float] = {}
    for node in nx.topological_sort(graph):
        a = by_id[node]
        duration = float(a["planned_duration"] or 1)
        actual_start = offset(a["actual_start"]) if dd is not None else None
        actual_finish = offset(a["actual_finish"]) if dd is not None else None
        if actual_start is not None and actual_finish is not None:
            es[node], ef[node] = actual_start, actual_finish + 1
        elif actual_start is not None:
            remaining = duration * (1 - min(float(a["percent_complete"] or 0), 99) / 100)
            es[node], ef[node] = actual_start, max(dd, actual_start) + remaining
        else:
            start = 0.0
            for p in graph.predecessors(node):
                edge = graph[p][node]
                start = max(start, {"FS": ef[p], "SS": es[p], "FF": ef[p] - duration, "SF": es[p] - duration}.get(edge["type"], ef[p]) + edge["lag"])
            if dd is not None:
                start = max(start, dd)
            es[node], ef[node] = start, start + duration
    project_finish = max(ef.values(), default=0)
    ls: dict[int, float] = {}
    lf: dict[int, float] = {}
    for node in reversed(list(nx.topological_sort(graph))):
        span = ef[node] - es[node]
        finish = project_finish
        for s in graph.successors(node):
            edge = graph[node][s]
            finish = min(finish, {"FS": ls[s], "SS": ls[s] + span, "FF": lf[s], "SF": lf[s] + span}.get(edge["type"], ls[s]) - edge["lag"])
        lf[node], ls[node] = finish, finish - span

    def as_date(day_offset: float) -> str:
        return (origin + timedelta(days=math.ceil(day_offset - 1e-9))).isoformat()

    result = {}
    for node in graph.nodes:
        done = by_id[node]["actual_finish"] is not None and dd is not None
        total_float = None if done else round(ls[node] - es[node], 2)  # float is meaningless for finished work
        result[node] = {
            "activity_code": by_id[node]["activity_code"],
            "early_start": es[node], "early_finish": ef[node], "late_start": ls[node], "late_finish": lf[node],
            "early_start_date": as_date(es[node]), "early_finish_date": as_date(ef[node] - 1),
            "total_float": total_float, "critical": not done and abs(total_float) < 0.001,
            "project_finish": project_finish, "project_finish_date": as_date(project_finish - 1),
        }
    return result


class ScheduleCycle(ValueError):
    pass


def is_milestone(activity: sqlite3.Row) -> bool:
    return activity["planned_start"] == activity["planned_finish"] or "milestone" in (activity["description"] or "").lower()


AT_RISK_FLOAT_DAYS = 2


def risk_reason(activity: sqlite3.Row, cpm: dict[str, Any], today: date) -> str | None:
    """At-risk rule (deterministic): an activity that is not complete is at risk when
    (1) it has not started although its planned start has passed, or
    (2) its CPM forecast finish (from actuals, remaining work and logic) is later than its planned finish
        AND its total float is below AT_RISK_FLOAT_DAYS, i.e. the slip cannot be absorbed."""
    if activity["status"] == "complete" or activity["actual_finish"]:
        return None
    planned_start, planned_finish = parse_day(activity["planned_start"]), parse_day(activity["planned_finish"])
    if not activity["actual_start"] and planned_start and planned_start < today:
        return f"late start: planned {planned_start.isoformat()}, not started"
    forecast = parse_day(cpm["early_finish_date"])
    if planned_finish and forecast and forecast > planned_finish and cpm["total_float"] < AT_RISK_FLOAT_DAYS:
        return f"forecast finish {forecast.isoformat()} after planned {planned_finish.isoformat()}, float {cpm['total_float']}d"
    return None


def recompute(db: sqlite3.Connection, project_id: int, reason: str) -> dict[str, Any]:
    today = date.today()
    state = cpm_state(db, project_id, today)
    serialized = json.dumps(state)
    finish = max((v["project_finish"] for v in state.values()), default=0)
    finish_date = next(iter(state.values()))["project_finish_date"] if state else None
    db.execute("INSERT INTO schedule_snapshots(project_id,reason,created_at,project_finish,state_json,data_date) VALUES (?,?,?,?,?,?)", (project_id, reason, now(), finish, serialized, today.isoformat()))
    for activity_id, values in state.items():
        db.execute("INSERT OR REPLACE INTO cpm_state(activity_id,early_start,early_finish,late_start,late_finish,total_float,critical,project_finish,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (activity_id, values["early_start_date"], values["early_finish_date"], values["late_start"], values["late_finish"], values["total_float"], int(values["critical"]), finish, now()))
    for activity in db.execute("SELECT * FROM activities WHERE project_id=?", (project_id,)).fetchall():
        why = risk_reason(activity, state[activity["id"]], today)
        db.execute("UPDATE activities SET at_risk=?, at_risk_reason=? WHERE id=?", (int(why is not None), why, activity["id"]))
    db.commit()
    return {"project_finish": finish, "project_finish_date": finish_date, "critical": [k for k, v in state.items() if v["critical"]], "state": state}


def cpm_impact(db: sqlite3.Connection, project_id: int, before: dict[str, Any], after: dict[str, Any], updated_id: int) -> dict[str, Any]:
    """Compare two recompute() results for the planner: finish movement, critical path, float, risk, milestones."""
    b, a = before["state"], after["state"]
    code = lambda i: a[i]["activity_code"]
    graph = nx.DiGraph()
    graph.add_edges_from((e["predecessor_id"], e["successor_id"]) for e in db.execute("SELECT predecessor_id, successor_id FROM activity_dependencies WHERE project_id=?", (project_id,)))
    downstream = nx.descendants(graph, updated_id) if updated_id in graph else set()
    acts = db.execute("SELECT * FROM activities WHERE project_id=?", (project_id,)).fetchall()
    return {
        "project_finish_before": before["project_finish_date"], "project_finish_after": after["project_finish_date"],
        "project_finish_change_days": round(after["project_finish"] - before["project_finish"], 2),
        "critical_entered": [code(i) for i in a if a[i]["critical"] and not b[i]["critical"]],
        "critical_left": [code(i) for i in a if b[i]["critical"] and not a[i]["critical"]],
        "float_changes": [{"activity_code": code(i), "before": b[i]["total_float"], "after": a[i]["total_float"]} for i in sorted(downstream) if b[i]["total_float"] != a[i]["total_float"]],
        "at_risk": [r["activity_code"] for r in acts if r["at_risk"]],
        "milestones": [{"activity_code": r["activity_code"], "before": b[r["id"]]["early_finish_date"], "after": a[r["id"]]["early_finish_date"]} for r in acts if is_milestone(r) and b[r["id"]]["early_finish_date"] != a[r["id"]]["early_finish_date"]],
    }


DELAY_CAUSES = ["material", "manpower", "equipment", "weather", "design_change", "permit_hse", "predecessor", "access", "quality_rework", "other"]


def activity_type(description: str) -> str:
    """Identifier-free activity pattern, e.g. 'Erect line XX102 spool 002' -> 'erect line spool'."""
    words = [w for w in norm(description).split() if not any(c.isdigit() for c in w) and len(w) > 2 and w not in {"and", "the", "for", "with"}]
    return " ".join(words[:3])


def actual_metrics(activity: Any) -> dict[str, Any]:
    """Planned-vs-actual numbers. Actual duration exists only when both actual dates exist."""
    ps, pf = parse_day(activity["planned_start"]), parse_day(activity["planned_finish"])
    as_, af = parse_day(activity["actual_start"]), parse_day(activity["actual_finish"])
    actual_duration = (af - as_).days + 1 if as_ and af else None
    return {
        "actual_duration": actual_duration,
        "start_variance": (as_ - ps).days if as_ and ps else None,
        "finish_variance": (af - pf).days if af and pf else None,
        "duration_variance": actual_duration - activity["planned_duration"] if actual_duration is not None and activity["planned_duration"] else None,
    }


def record_delay_cause(db: sqlite3.Connection, project_id: int, event_id: int, activity_id: int | None, cause: str, notes: str) -> None:
    if cause not in DELAY_CAUSES:
        raise HTTPException(422, f"delay cause must be one of {', '.join(DELAY_CAUSES)}")
    db.execute("INSERT INTO delay_causes(event_id,cause,notes,project_id,activity_id,created_at) VALUES (?,?,?,?,?,?)", (event_id, cause, notes, project_id, activity_id, now()))
    if activity_id:
        db.execute("UPDATE execution_memory SET delay_cause=?, notes=? WHERE activity_id=?", (cause, notes, activity_id))


def upsert_memory(db: sqlite3.Connection, activity_id: int) -> None:
    """Execution memory is written from confirmed actuals only; the latest delay cause for the activity is kept."""
    a = db.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
    cause = db.execute("SELECT cause, notes FROM delay_causes WHERE activity_id=? ORDER BY id DESC LIMIT 1", (activity_id,)).fetchone()
    m = actual_metrics(a)
    db.execute(
        "INSERT OR REPLACE INTO execution_memory(activity_id,project_id,activity_code,activity_type,discipline,location,planned_start,planned_finish,planned_duration,"
        "actual_start,actual_finish,actual_duration,start_variance,finish_variance,duration_variance,delay_cause,notes,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (a["id"], a["project_id"], a["activity_code"], activity_type(a["description"]), a["discipline"], a["location"], a["planned_start"], a["planned_finish"], a["planned_duration"],
         a["actual_start"], a["actual_finish"], m["actual_duration"], m["start_variance"], m["finish_variance"], m["duration_variance"],
         cause["cause"] if cause else None, cause["notes"] if cause else None, now()),
    )


def apply_update(db: sqlite3.Connection, project_id: int, event_id: int, activity_id: int, actor: str, comment: str = "", delay_cause: str | None = None) -> dict[str, Any]:
    """Write a human-confirmed actual. Callers must have checked the decision state."""
    event = db.execute("SELECT * FROM execution_events WHERE id=?", (event_id,)).fetchone()
    decision = db.execute("SELECT * FROM match_decisions WHERE event_id=? ORDER BY id DESC LIMIT 1", (event_id,)).fetchone()
    activity = db.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
    if not activity:
        raise HTTPException(404, "Activity not found")
    if activity["project_id"] != project_id:
        raise HTTPException(409, "Activity belongs to a different project than the report")
    started = event["progress"] is None and started_signal(event["source_text"])
    if event["progress"] is None and not started:
        why = " (its completion/start wording is negated or future tense)" if NEGATED_OR_FUTURE.search(norm(event["source_text"])) else ""
        raise HTTPException(422, f"Report carries no progress or start information to apply{why}. Reject it or wait for an actual update.")
    # Progress is monotonic (audit F-02): a field report never reopens or lowers an activity.
    # There is no override workflow in this build; the planner rejects the report instead.
    current = float(activity["percent_complete"] or 0)
    if activity["status"] == "complete" or current >= 100 or activity["actual_finish"]:
        if event["progress"] is None or event["progress"] < 100:
            raise HTTPException(409, f"{activity['activity_code']} is already complete; lower progress requires explicit planner override. Nothing was written; reject this report if it is wrong.")
    elif event["progress"] is not None and event["progress"] < current:
        raise HTTPException(409, f"Reported progress {event['progress']:g}% is lower than the current {current:g}% of {activity['activity_code']}; progress is never decreased silently. Nothing was written.")
    before = recompute(db, project_id, "pre-update snapshot")
    old = {"percent_complete": activity["percent_complete"], "actual_start": activity["actual_start"], "actual_finish": activity["actual_finish"], "status": activity["status"]}
    progress = event["progress"] if event["progress"] is not None else old["percent_complete"]
    status = "complete" if progress >= 100 else "in_progress" if progress > 0 or started else old["status"]
    actual_start = old["actual_start"] or event["event_timestamp"] if progress > 0 or started else old["actual_start"]
    actual_finish = old["actual_finish"] or event["event_timestamp"] if progress >= 100 else old["actual_finish"]  # a repeat 100% keeps the first finish date
    new = {"percent_complete": progress, "actual_start": actual_start, "actual_finish": actual_finish, "status": status}
    # Human decision is appended; the system's original decision row is kept for provenance.
    kind = "approved" if activity_id == decision["activity_id"] else "manual_association" if decision["decision"] == "UNMATCHED" else "reassigned"
    try:
        db.execute("INSERT INTO match_decisions(event_id,decision,activity_id,top_score,second_score,margin,actor,comment,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (event_id, "APPROVED", activity_id, decision["top_score"], decision["second_score"], decision["margin"], actor, comment, now()))
    except sqlite3.IntegrityError:
        # A concurrent confirmation won the race; the one_approval_per_event index kept it single.
        db.rollback()
        raise HTTPException(409, "Event is already approved")
    db.execute("UPDATE activities SET percent_complete=?,actual_start=?,actual_finish=?,status=? WHERE id=?", (progress, actual_start, actual_finish, status, activity_id))
    db.execute("UPDATE execution_events SET status='APPROVED' WHERE id=?", (event_id,))
    audit_id = db.execute("INSERT INTO audit_log(project_id,activity_id,event_id,old_value,new_value,source,evidence,score,actor,approval_status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (project_id, activity_id, event_id, json.dumps(old), json.dumps(new), "field_report", event["source_text"], decision["top_score"], actor, kind, now())).lastrowid
    if delay_cause:
        record_delay_cause(db, project_id, event_id, activity_id, delay_cause, comment)
    upsert_memory(db, activity_id)
    after = recompute(db, project_id, "confirmed actual update")
    db.commit()
    audit_row = dict(db.execute("SELECT * FROM audit_log WHERE id=?", (audit_id,)).fetchone())
    return {"activity": {"id": activity_id, "activity_code": activity["activity_code"], "description": activity["description"]}, "old": old, "new": new, "before": before, "after": after, "impact": cpm_impact(db, project_id, before, after, activity_id), "audit": audit_row, "approval_status": kind, "critical_path_changed": before["critical"] != after["critical"]}


def event_project(db: sqlite3.Connection, event_id: int) -> int:
    row = db.execute("SELECT r.project_id FROM execution_events e JOIN field_reports r ON r.id=e.report_id WHERE e.id=?", (event_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Event not found")
    return row["project_id"]


def latest_decision(db: sqlite3.Connection, event_id: int) -> sqlite3.Row:
    row = db.execute("SELECT * FROM match_decisions WHERE event_id=? ORDER BY id DESC LIMIT 1", (event_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Match decision not found")
    if row["decision"] in ("APPROVED", "REJECTED"):
        # APPROVED and REJECTED are terminal: no double write, no silent undo of a schedule change.
        raise HTTPException(409, f"Event is already {row['decision'].lower()}")
    return row


class ReportIn(BaseModel):
    project_id: int = 1
    text: str = Field(min_length=1, max_length=20000)
    source: str = "text"
    report_date: date | None = None  # the day the report describes; defaults to today
    # Optional client-generated id: a retried submission (e.g. mobile after a timeout) replays the
    # original result instead of creating a second event.
    client_report_id: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("report_date")
    @classmethod
    def not_in_future(cls, value: date | None) -> date | None:
        # A future date would become an actual start/finish on confirmation (audit F-08).
        if value and value > date.today():
            raise ValueError("report_date cannot be in the future")
        return value


class DecisionIn(BaseModel):
    activity_id: int | None = None
    actor: str = "planner"
    comment: str = ""
    delay_cause: str | None = None


class DelayCauseIn(BaseModel):
    cause: str
    notes: str = ""


class AgentIn(BaseModel):
    project_id: int = 1
    text: str = Field(min_length=1, max_length=20000)
    session_id: str | None = None


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ProgressSync AI", version="1.2.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND / "assets", check_dir=False), name="assets")


def configured_origins() -> list[str]:
    configured = os.getenv("PROGRESSSYNC_CORS_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:5173", "http://127.0.0.1:5173"]


@app.middleware("http")
async def demo_auth(request: Request, call_next):
    token = os.getenv("PROGRESSSYNC_API_TOKEN", "")
    protected = request.url.path == "/api/v1" or request.url.path.startswith("/api/v1/")
    if token and protected and request.method != "OPTIONS":
        authorization = request.headers.get("authorization", "")
        scheme, _, presented = authorization.partition(" ")
        if scheme.lower() != "bearer" or not presented or not secrets.compare_digest(presented, token):
            return JSONResponse(status_code=401, content={"detail": "Authentication required"}, headers={"WWW-Authenticate": "Bearer"})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(ScheduleCycle)
def schedule_cycle(_request, exc: ScheduleCycle) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(SemanticModelMissing)
def semantic_model_missing(_request, exc: SemanticModelMissing) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})

@app.get("/", include_in_schema=False)
def index():
    if (FRONTEND / "index.html").exists():
        return FileResponse(FRONTEND / "index.html")
    return JSONResponse(status_code=503, content={"detail": "React UI not built. Run: cd frontend-react && npm ci && npm run build (or use npm run dev on :5173)."})

@app.get("/api/v1/projects")
def projects():
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY id")]

@app.post("/api/v1/projects")
def create_project(payload: ProjectIn):
    with closing(connect()) as db:
        project_id = db.execute("INSERT INTO projects(name, created_at) VALUES (?, ?)", (payload.name.strip(), now())).lastrowid
        db.commit()
        return dict(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())

@app.get("/api/v1/projects/{project_id}/activities")
def activities(project_id: int):
    with closing(connect()) as db:
        refresh_if_stale(db, project_id)
        return [dict(row) for row in db.execute("SELECT a.*, c.early_start, c.early_finish, c.total_float, c.critical FROM activities a LEFT JOIN cpm_state c ON a.id=c.activity_id WHERE a.project_id=? ORDER BY a.id", (project_id,))]

@app.get("/api/v1/projects/{project_id}/dependencies")
def dependencies(project_id: int):
    with closing(connect()) as db:
        return [dict(row) for row in db.execute(
            "SELECT d.id, d.predecessor_id, p.activity_code AS predecessor_code, d.successor_id, s.activity_code AS successor_code, d.dependency_type, d.lag "
            "FROM activity_dependencies d JOIN activities p ON p.id=d.predecessor_id JOIN activities s ON s.id=d.successor_id WHERE d.project_id=? ORDER BY d.id",
            (project_id,))]

@app.get("/api/v1/activities/{activity_id}")
def activity(activity_id: int):
    with closing(connect()) as db:
        row = db.execute("SELECT a.*, c.* FROM activities a LEFT JOIN cpm_state c ON a.id=c.activity_id WHERE a.id=?", (activity_id,)).fetchone()
        if not row: raise HTTPException(404, "Activity not found")
        return dict(row)

@app.post("/api/v1/reports")
def report(payload: ReportIn):
    started = time.perf_counter()
    with closing(connect()) as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (payload.project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        if payload.client_report_id:
            prior = replayed_report(db, payload)
            if prior:
                return prior
        try:
            report_id = db.execute("INSERT INTO field_reports(project_id,source,raw_text,submitted_at,client_report_id) VALUES (?,?,?,?,?)", (payload.project_id, payload.source, payload.text, now(), payload.client_report_id)).lastrowid
        except sqlite3.IntegrityError:
            return replayed_report(db, payload)
        event = extract_event(payload.text, payload.source, report_id, payload.report_date)
        event_id = db.execute("INSERT INTO execution_events(report_id,event_type,discipline,activity_terms,identifiers,location_terms,quantity,unit,progress,event_timestamp,source_text,source_span,extraction_confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (report_id, event["event_type"], event["discipline"], event["activity_terms"], json.dumps(event["identifiers"]), event["location_terms"], event["quantity"], event["unit"], event["progress"], event["event_timestamp"], event["source_text"], json.dumps(event["source_span"]), event["extraction_confidence"])).lastrowid
        event["id"] = event_id
        match = make_match(db, payload.project_id, event_id, event)
        latency = round((time.perf_counter() - started) * 1000, 2)
        result = {"report_id": report_id, "event_id": event_id, "event": event, "match": match, "latency_ms": latency}
        db.execute("UPDATE field_reports SET latency_ms=?,status=?,response_json=? WHERE id=?", (latency, match["decision"], json.dumps(result) if payload.client_report_id else None, report_id))
        db.commit()
        return result


def replayed_report(db: sqlite3.Connection, payload: ReportIn) -> dict[str, Any] | None:
    """The original response for a client_report_id already seen in this project; 409 if the id was
    reused for different text or the first request is still being processed."""
    row = db.execute("SELECT raw_text, response_json FROM field_reports WHERE project_id=? AND client_report_id=?", (payload.project_id, payload.client_report_id)).fetchone()
    if not row:
        return None
    if row["raw_text"] != payload.text:
        raise HTTPException(409, "client_report_id was already used for a different report")
    if not row["response_json"]:
        raise HTTPException(409, "This report is still being processed; retry shortly")
    return {**json.loads(row["response_json"]), "replayed": True}

@app.get("/api/v1/events/{event_id}")
def event(event_id: int):
    with closing(connect()) as db:
        row = db.execute("SELECT * FROM execution_events WHERE id=?", (event_id,)).fetchone()
        if not row: raise HTTPException(404, "Event not found")
        data = dict(row); data["project_id"] = event_project(db, event_id); data["identifiers"] = json.loads(data["identifiers"] or "[]"); data["source_span"] = json.loads(data["source_span"] or "[]")
        data["decision"] = dict(db.execute("SELECT * FROM match_decisions WHERE event_id=? ORDER BY id DESC LIMIT 1", (event_id,)).fetchone() or {})
        return data

@app.get("/api/v1/events/{event_id}/candidates")
def candidates(event_id: int):
    with closing(connect()) as db:
        rows = db.execute("SELECT c.*, a.activity_code, a.description, a.discipline, a.location, a.wbs_path FROM match_candidates c JOIN activities a ON a.id=c.activity_id WHERE c.event_id=? ORDER BY c.rank", (event_id,)).fetchall()
        result = [dict(row) for row in rows]
        for item in result: item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
        return result

@app.get("/api/v1/review-queue")
def review_queue(project_id: int | None = None):
    with closing(connect()) as db:
        return [dict(row) for row in db.execute(
            "SELECT e.*, r.project_id, d.decision, d.comment AS reason, d.top_score, d.second_score, d.margin, d.activity_id FROM execution_events e "
            "JOIN field_reports r ON r.id=e.report_id "
            "JOIN match_decisions d ON d.id=(SELECT MAX(id) FROM match_decisions WHERE event_id=e.id) "
            "WHERE d.decision IN ('REVIEW_REQUIRED','UNMATCHED') AND (? IS NULL OR r.project_id=?) ORDER BY e.id DESC",
            (project_id, project_id))]

@app.get("/api/v1/awaiting-confirmation")
def awaiting_confirmation(project_id: int | None = None):
    """AUTO_MATCHED events nobody has confirmed or rejected yet (audit F-03): they must stay reachable
    even if the ingest screen or a Time Agent conversation was abandoned."""
    with closing(connect()) as db:
        return [dict(row) for row in db.execute(
            "SELECT e.id, e.source_text, e.progress, e.event_timestamp, r.project_id, r.source, r.submitted_at, "
            "d.decision, d.comment AS reason, d.top_score, d.second_score, d.margin, d.activity_id, a.activity_code, a.description "
            "FROM execution_events e JOIN field_reports r ON r.id=e.report_id "
            "JOIN match_decisions d ON d.id=(SELECT MAX(id) FROM match_decisions WHERE event_id=e.id) "
            "LEFT JOIN activities a ON a.id=d.activity_id "
            "WHERE d.decision='AUTO_MATCHED' AND (? IS NULL OR r.project_id=?) ORDER BY e.id DESC",
            (project_id, project_id))]

@app.post("/api/v1/events/{event_id}/send-to-review")
def send_event_to_review(event_id: int, payload: DecisionIn):
    with closing(connect()) as db:
        event_project(db, event_id)
        if latest_decision(db, event_id)["decision"] != "AUTO_MATCHED":
            raise HTTPException(409, "Only a pending AUTO_MATCHED event can be sent to review")
        send_to_review(db, event_id, f"planner sent to review: {payload.comment}" if payload.comment else "planner sent to review")
        db.commit()
        return {"event_id": event_id, "decision": "REVIEW_REQUIRED"}

@app.post("/api/v1/events/{event_id}/confirm")
def confirm(event_id: int, payload: DecisionIn):
    with closing(connect()) as db:
        project_id = event_project(db, event_id)
        decision = latest_decision(db, event_id)
        # Only a confident system match may be confirmed without naming the activity.
        activity_id = payload.activity_id or (decision["activity_id"] if decision["decision"] == "AUTO_MATCHED" else None)
        if not activity_id:
            raise HTTPException(400, f"activity_id is required to confirm a {decision['decision']} event")
        if payload.delay_cause and payload.delay_cause not in DELAY_CAUSES:
            raise HTTPException(422, f"delay cause must be one of {', '.join(DELAY_CAUSES)}")
        return apply_update(db, project_id, event_id, activity_id, payload.actor, payload.comment, payload.delay_cause)

@app.post("/api/v1/events/{event_id}/delay-cause")
def add_delay_cause(event_id: int, payload: DelayCauseIn):
    with closing(connect()) as db:
        project_id = event_project(db, event_id)
        approved = db.execute("SELECT activity_id FROM match_decisions WHERE event_id=? AND decision='APPROVED'", (event_id,)).fetchone()
        record_delay_cause(db, project_id, event_id, approved["activity_id"] if approved else None, payload.cause, payload.notes)
        db.commit()
        return {"event_id": event_id, "cause": payload.cause, "activity_id": approved["activity_id"] if approved else None}

@app.get("/api/v1/delay-cause-categories")
def delay_cause_categories():
    return DELAY_CAUSES

@app.post("/api/v1/events/{event_id}/reject")
def reject(event_id: int, payload: DecisionIn):
    with closing(connect()) as db:
        event_project(db, event_id)
        decision = latest_decision(db, event_id)
        db.execute("INSERT INTO match_decisions(event_id,decision,activity_id,top_score,second_score,margin,actor,comment,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (event_id, "REJECTED", None, decision["top_score"], decision["second_score"], decision["margin"], payload.actor, payload.comment, now()))
        db.execute("UPDATE execution_events SET status='REJECTED' WHERE id=?", (event_id,))
        db.commit()
        return {"event_id": event_id, "decision": "REJECTED"}

@app.post("/api/v1/projects/{project_id}/recompute")
def recompute_api(project_id: int):
    with closing(connect()) as db: return recompute(db, project_id, "manual recompute")

@app.get("/api/v1/projects/{project_id}/critical-path")
def critical_path(project_id: int):
    with closing(connect()) as db:
        refresh_if_stale(db, project_id)
        return [dict(row) for row in db.execute("SELECT a.*, c.total_float, c.critical FROM activities a JOIN cpm_state c ON a.id=c.activity_id WHERE a.project_id=? AND c.critical=1 ORDER BY c.early_start", (project_id,))]

@app.get("/api/v1/projects/{project_id}/snapshots/{snapshot_id}/diff")
def snapshot_diff(project_id: int, snapshot_id: int):
    with closing(connect()) as db:
        current = db.execute("SELECT * FROM schedule_snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        old = db.execute("SELECT * FROM schedule_snapshots WHERE project_id=? AND id=?", (project_id, snapshot_id)).fetchone()
        if not old or not current: raise HTTPException(404, "Snapshot not found")
        before, after = json.loads(old["state_json"]), json.loads(current["state_json"])
        return {"from": old["id"], "to": current["id"], "project_finish_change": current["project_finish"] - old["project_finish"], "critical_entered": [k for k in after if after[k]["critical"] and not before.get(k, {}).get("critical")], "critical_left": [k for k in before if before[k]["critical"] and not after.get(k, {}).get("critical")], "float_warnings": [k for k, value in after.items() if value["total_float"] is not None and value["total_float"] <= 1]}

@app.get("/api/v1/ml/status")
def ml_status():
    artifact_exists = RERANKER_MODEL_PATH.exists()
    artifact_version = None

    if artifact_exists:
        try:
            artifact = get_reranker()
            if artifact:
                artifact_version = artifact.get("version")
        except Exception:
            artifact_version = None

    try:
        get_semantic_model()
        semantic_available = True
    except SemanticModelMissing as exc:
        semantic_available = False
        semantic_error = str(exc)
    except Exception as exc:
        LOGGER.exception("Unexpected semantic model status failure")
        semantic_available = False
        semantic_error = f"{type(exc).__name__}: {exc}"

    response = {
        "semantic_model": SEMANTIC_MODEL_NAME,
        "semantic_model_revision": SEMANTIC_MODEL_REVISION,
        "semantic_model_available": semantic_available,
        "reranker_enabled": RERANKER_ENABLED,
        "reranker_artifact_exists": artifact_exists,
        "reranker_version": artifact_version,
        "reranker_auto_threshold": RERANKER_AUTO_THRESHOLD,
        "reranker_margin_threshold": RERANKER_MARGIN_THRESHOLD,
    }
    if not semantic_available:
        response["semantic_model_error"] = semantic_error
    return response


def _mean(values: list[Any]) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


@app.get("/api/v1/analytics/discipline-productivity")
def productivity(project_id: int | None = None):
    """Per discipline and activity type. Actual duration averages only activities with both actual dates."""
    with closing(connect()) as db:
        rows = db.execute("SELECT * FROM activities WHERE (? IS NULL OR project_id=?)", (project_id, project_id)).fetchall()
    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for r in rows:
        groups[(r["discipline"], activity_type(r["description"]))].append(r)
    return [{
        "discipline": discipline, "activity_type": kind, "activities": len(items),
        "progress": _mean([r["percent_complete"] or 0 for r in items]),
        "completed": sum(1 for r in items if r["actual_finish"]),
        "avg_planned_duration": _mean([r["planned_duration"] for r in items]),
        "avg_actual_duration": _mean([actual_metrics(r)["actual_duration"] for r in items]),
    } for (discipline, kind), items in sorted(groups.items())]

@app.get("/api/v1/analytics/variance")
def variance(project_id: int | None = None):
    """Planned vs actual for every activity that has at least an actual start (days; positive = late/longer)."""
    with closing(connect()) as db:
        rows = db.execute("SELECT * FROM activities WHERE actual_start IS NOT NULL AND (? IS NULL OR project_id=?) ORDER BY planned_start", (project_id, project_id)).fetchall()
    items = [{"activity_code": r["activity_code"], "description": r["description"], "discipline": r["discipline"], "status": r["status"],
              "planned_start": r["planned_start"], "planned_finish": r["planned_finish"], "planned_duration": r["planned_duration"],
              "actual_start": r["actual_start"], "actual_finish": r["actual_finish"], **actual_metrics(r)} for r in rows]
    return {"activities": items, "summary": {
        "with_actual_start": len(items), "completed": sum(1 for i in items if i["actual_finish"]),
        "avg_start_variance": _mean([i["start_variance"] for i in items]),
        "avg_finish_variance": _mean([i["finish_variance"] for i in items]),
        "avg_duration_variance": _mean([i["duration_variance"] for i in items]),
    }}

@app.get("/api/v1/analytics/wbs-progress")
def wbs_progress(project_id: int | None = None):
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT wbs_path, ROUND(AVG(percent_complete),1) progress, COUNT(*) activities FROM activities WHERE (? IS NULL OR project_id=?) GROUP BY wbs_path ORDER BY wbs_path", (project_id, project_id))]

@app.get("/api/v1/analytics/delay-causes")
def delay_causes(project_id: int | None = None):
    with closing(connect()) as db:
        rows = db.execute("SELECT cause, created_at FROM delay_causes WHERE (? IS NULL OR project_id=?)", (project_id, project_id)).fetchall()
    counts = Counter(r["cause"] for r in rows)
    weekly = Counter((date.fromisoformat(r["created_at"][:10]).strftime("%G-W%V"), r["cause"]) for r in rows if r["created_at"])
    return {"counts": [{"cause": c, "count": n} for c, n in counts.most_common()],
            "weekly": [{"week": w, "cause": c, "count": n} for (w, c), n in sorted(weekly.items())]}

@app.get("/api/v1/memory/similar")
def memory(project_id: int | None = None, discipline: str | None = None, location: str | None = None, activity_type: str | None = None, description: str = ""):
    """Search execution memory (confirmed actuals). Filters are exact on discipline/location; activity type and
    description rank by string similarity. Omit project_id to search all projects' history."""
    with closing(connect()) as db:
        rows = [dict(r) for r in db.execute(
            "SELECT m.*, a.description FROM execution_memory m JOIN activities a ON a.id=m.activity_id "
            "WHERE (? IS NULL OR m.project_id=?) AND (? IS NULL OR m.discipline=?) AND (? IS NULL OR lower(m.location)=lower(?))",
            (project_id, project_id, discipline or None, discipline or None, location or None, location or None))]
    query = " ".join(filter(None, [activity_type, description]))
    for row in rows:
        row["similarity"] = round(max(similarity(query, row["description"]), similarity(query, row["activity_type"] or "")), 3) if query else None
    rows.sort(key=lambda r: (r["similarity"] or 0, r["updated_at"]), reverse=True)
    return rows[:20]

@app.get("/api/v1/memory/summary")
def memory_summary(project_id: int | None = None):
    with closing(connect()) as db:
        rows = db.execute("SELECT * FROM execution_memory WHERE (? IS NULL OR project_id=?)", (project_id, project_id)).fetchall()
    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for r in rows:
        groups[(r["discipline"], r["activity_type"])].append(r)
    return [{
        "discipline": d, "activity_type": t, "records": len(items), "completed": sum(1 for r in items if r["actual_duration"] is not None),
        "avg_actual_duration": _mean([r["actual_duration"] for r in items]),
        "avg_duration_variance": _mean([r["duration_variance"] for r in items]),
        "top_delay_cause": (Counter(r["delay_cause"] for r in items if r["delay_cause"]).most_common(1) or [[None]])[0][0],
    } for (d, t), items in sorted(groups.items())]

@app.get("/api/v1/audit")
def audit(project_id: int | None = None):
    with closing(connect()) as db:
        return [dict(row) for row in db.execute(
            "SELECT l.*, a.activity_code, a.description FROM audit_log l LEFT JOIN activities a ON a.id=l.activity_id "
            "WHERE (? IS NULL OR l.project_id=?) ORDER BY l.id DESC LIMIT 100", (project_id, project_id))]

@app.get("/api/v1/audit/export")
def audit_export(project_id: int | None = None):
    rows = audit(project_id)
    output = io.StringIO()
    fields = ["id", "project_id", "activity_id", "event_id", "activity_code", "description", "old_value", "new_value", "source", "evidence", "score", "actor", "approval_status", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit.csv"})

@app.get("/api/v1/terminology-map")
def terminology():
    with closing(connect()) as db: return [dict(row) for row in db.execute("SELECT * FROM terminology_map ORDER BY field_term")]

# --- Time Agent: session-backed clarification over the same report pipeline -----------------------

MAX_CLARIFY_ROUNDS = 2
YES = re.compile(r"^\s*(?:yes|y|yeah|yep|confirm(?:ed)?|ok(?:ay)?|correct|right)\b", re.I)
NO = re.compile(r"^\s*(?:no|n|nope|wrong|incorrect)\b", re.I)


def missing_progress(event: Any) -> bool:
    return event["progress"] is None and not started_signal(event["source_text"])


def clarification_question(event: Any, match: dict[str, Any], top: list[dict[str, Any]]) -> str:
    """Ask for the piece of context that would actually separate the candidates."""
    if match["decision"] == "UNMATCHED":
        return "I can't place this in the schedule. Which line, equipment tag or activity is it, and at which location?"
    locations = sorted({c["location"] for c in top if c["location"]})
    same_id = [c for c in top if c["score_id"] >= 1.0]
    if len(same_id) > 1:
        return "Which one do you mean: " + "; ".join(f"{c['activity_code']} ({c['description']}, {c['location']})" for c in same_id) + "? Reply with the code or the location."
    if not event["location_terms"] and len(locations) > 1:
        return f"Which location is this at: {', '.join(locations)}?"
    if not event["location_terms"]:
        return f"Where is this work? My best guess is {top[0]['activity_code']} ({top[0]['description']}) at {top[0]['location']}. Tell me the location or rack."
    if not event["discipline"]:
        return "Which crew or discipline is this (piping, civil, electrical, instrumentation...)?"
    if missing_progress(event):
        return "What should I record: a percentage, started, or completed?"
    return "The closest activities are " + "; ".join(f"{c['activity_code']} ({c['description']})" for c in top[:3]) + ". Which one is it? Reply with the code."


def send_to_review(db: sqlite3.Connection, event_id: int, reason: str) -> None:
    last = db.execute("SELECT * FROM match_decisions WHERE event_id=? ORDER BY id DESC LIMIT 1", (event_id,)).fetchone()
    db.execute("INSERT INTO match_decisions(event_id,decision,activity_id,top_score,second_score,margin,actor,comment,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (event_id, "REVIEW_REQUIRED", last["activity_id"], last["top_score"], last["second_score"], last["margin"], "time_agent", reason, now()))
    db.execute("UPDATE execution_events SET status='REVIEW_REQUIRED' WHERE id=?", (event_id,))


def rematch_event(db: sqlite3.Connection, project_id: int, event_id: int, text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fold a clarification into the same pending event and run the normal matcher again.
    The superseded candidate rows are replaced; every decision row (with its scores) is kept."""
    report_id = db.execute("SELECT report_id FROM execution_events WHERE id=?", (event_id,)).fetchone()["report_id"]
    event = extract_event(text, "time_agent", report_id)
    db.execute("UPDATE execution_events SET discipline=?,activity_terms=?,identifiers=?,location_terms=?,quantity=?,unit=?,progress=?,source_text=?,source_span=?,extraction_confidence=? WHERE id=?",
               (event["discipline"], event["activity_terms"], json.dumps(event["identifiers"]), event["location_terms"], event["quantity"], event["unit"], event["progress"], event["source_text"], json.dumps(event["source_span"]), event["extraction_confidence"], event_id))
    db.execute("DELETE FROM match_candidates WHERE event_id=?", (event_id,))
    event["id"] = event_id
    return event, make_match(db, project_id, event_id, event)


def top_candidates(db: sqlite3.Connection, event_id: int, limit: int = 3) -> list[dict[str, Any]]:
    return [dict(r) for r in db.execute("SELECT c.activity_id, c.score_id, c.fused_score, a.activity_code, a.description, a.location FROM match_candidates c JOIN activities a ON a.id=c.activity_id WHERE c.event_id=? ORDER BY c.rank LIMIT ?", (event_id, limit))]


def code_named(code: str, text: str) -> bool:
    """The supervisor named this activity code as a whole token (audit F-11): "A1" is not in "Area 1"."""
    return re.search(rf"(?<![\w-]){re.escape(code)}(?![\w-])", text, re.I) is not None


@app.post("/api/v1/agent/message")
def agent(payload: AgentIn):
    with closing(connect()) as db:
        if not db.execute("SELECT 1 FROM projects WHERE id=?", (payload.project_id,)).fetchone():
            raise HTTPException(404, "Project not found")
        session_id = payload.session_id or uuid.uuid4().hex
        session = db.execute("SELECT * FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
        if session and session["project_id"] != payload.project_id:
            # A conversation never crosses projects (audit F-10): start a fresh session instead of
            # reusing, resetting or exposing the other project's transcript.
            session_id, session = uuid.uuid4().hex, None
        if not session:
            db.execute("INSERT INTO agent_sessions(id,project_id,state,event_id,selected_activity_id,rounds,created_at,updated_at) VALUES (?,?,'idle',NULL,NULL,0,?,?)", (session_id, payload.project_id, now(), now()))
            session = db.execute("SELECT * FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
        state, event_id, selected, rounds = session["state"], session["event_id"], session["selected_activity_id"], session["rounds"]
        if event_id:
            last = db.execute("SELECT decision FROM match_decisions WHERE event_id=? ORDER BY id DESC LIMIT 1", (event_id,)).fetchone()
            if not last or last["decision"] in ("APPROVED", "REJECTED"):
                state, event_id, selected, rounds = "idle", None, None, 0  # decided elsewhere (e.g. by a planner)
        db.execute("INSERT INTO agent_messages(session_id,role,text,event_id,created_at) VALUES (?,?,?,?,?)", (session_id, "user", payload.text, event_id, now()))
        db.commit()  # release the write lock before report() opens its own connection

        text = payload.text.strip()
        confirmation, event, match = None, None, None
        pending = state in ("clarifying", "awaiting_confirmation")
        mentioned = next((c for c in top_candidates(db, event_id, 5) if code_named(c["activity_code"], text)), None) if pending else None

        if state == "awaiting_confirmation" and YES.match(text):
            decision = latest_decision(db, event_id)
            activity_id = selected or decision["activity_id"]
            confirmation = apply_update(db, payload.project_id, event_id, activity_id, f"supervisor via time agent {session_id[:8]}", "confirmed in Time Agent chat")
            old, new = confirmation["old"], confirmation["new"]
            reply = (f"Recorded on {confirmation['activity']['activity_code']}: status {old['status']} → {new['status']}, progress {old['percent_complete']:g}% → {new['percent_complete']:g}%, "
                     f"actual start {new['actual_start'] or '—'}, audit #{confirmation['audit']['id']}. Forecast project finish {confirmation['impact']['project_finish_before']} → {confirmation['impact']['project_finish_after']}.")
            state, event_id, selected, rounds = "idle", None, None, 0
        elif state == "awaiting_confirmation" and NO.match(text):
            send_to_review(db, event_id, "supervisor rejected the suggested activity in Time Agent")
            reply = f"Understood. Nothing was written; event #{event_id} is now in the planner review queue."
            state, event_id, selected, rounds = "idle", None, None, 0
        else:
            if mentioned:
                selected = mentioned["activity_id"]
                event = db.execute("SELECT * FROM execution_events WHERE id=?", (event_id,)).fetchone()
                match = {"decision": latest_decision(db, event_id)["decision"]}
            elif pending:
                current = db.execute("SELECT source_text FROM execution_events WHERE id=?", (event_id,)).fetchone()["source_text"]
                event, match = rematch_event(db, payload.project_id, event_id, f"{current} {text}")
                selected, rounds = None, rounds + 1
            else:
                result = report(ReportIn(project_id=payload.project_id, text=text, source="time_agent"))
                event_id, match, selected, rounds = result["event_id"], result["match"], None, 0
            event = db.execute("SELECT * FROM execution_events WHERE id=?", (event_id,)).fetchone()
            top = top_candidates(db, event_id)
            choice = next((c for c in top_candidates(db, event_id, 5) if c["activity_id"] == selected), None) if selected else (top[0] if match["decision"] == "AUTO_MATCHED" and top else None)
            if choice and not missing_progress(event):
                what = f"{event['progress']:g}% progress" if event["progress"] is not None else "actual start today"
                basis = "you picked it" if selected else f"score {match['top_score']:.3f}, margin {match['margin']:.3f}"
                reply = f"Matched to {choice['activity_code']} ({choice['description']}, {choice['location']}); {basis}. I will record {what}. Confirm? (yes / no)"
                state = "awaiting_confirmation"
            elif rounds < MAX_CLARIFY_ROUNDS:
                reply = clarification_question(event, match, top) if not (choice and missing_progress(event)) else "What should I record: a percentage, started, or completed?"
                state = "clarifying"
            else:
                if match["decision"] == "AUTO_MATCHED":
                    send_to_review(db, event_id, "Time Agent: no progress information after clarification")
                reply = f"I still can't be sure, so nothing was written. Event #{event_id} is in the planner review queue with its evidence."
                state, event_id, selected, rounds = "idle", None, None, 0

        db.execute("UPDATE agent_sessions SET state=?,event_id=?,selected_activity_id=?,rounds=?,updated_at=? WHERE id=?", (state, event_id, selected, rounds, now(), session_id))
        db.execute("INSERT INTO agent_messages(session_id,role,text,event_id,created_at) VALUES (?,?,?,?,?)", (session_id, "agent", reply, event_id, now()))
        db.commit()
        return {"session_id": session_id, "state": state, "reply": reply, "event_id": event_id or (confirmation and confirmation["audit"]["event_id"]),
                "match": match, "event": dict(event) if event else None, "confirmation": confirmation}


@app.get("/api/v1/agent/sessions/{session_id}")
def agent_session(session_id: str, project_id: int | None = None):
    with closing(connect()) as db:
        session = db.execute("SELECT * FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
        if not session or (project_id is not None and session["project_id"] != project_id):
            raise HTTPException(404, "Session not found")
        return {**dict(session), "messages": [dict(r) for r in db.execute("SELECT * FROM agent_messages WHERE session_id=? ORDER BY id", (session_id,))]}

@app.post("/api/v1/projects/{project_id}/schedule/import")
async def import_schedule(project_id: int, file: UploadFile = File(...), project_name: str | None = Form(None)):
    content = await file.read()
    if len(content) > 10_000_000: raise HTTPException(413, "File exceeds 10 MB limit")
    name = (file.filename or "").lower()
    if not (name.endswith(".csv") or name.endswith(".xlsx")): raise HTTPException(415, "Only CSV and XLSX schedules are supported")
    if name.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            values = list(sheet.values)
            headers, records = values[0], values[1:]
        except Exception as exc:
            raise HTTPException(400, f"Invalid XLSX: {exc}")
    else:
        try:
            text = content.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(text)); values = list(reader); headers, records = values[0], values[1:]
        except Exception as exc:
            raise HTTPException(400, f"Invalid CSV: {exc}")
    normalized_headers = {str(h).strip().lower() for h in headers if h is not None}
    # Two accepted layouts: an activity file (optional predecessor/relationship/lag columns), or a
    # dependency-only file with predecessor,successor[,relationship,lag] columns.
    dependency_file = {"predecessor", "successor"} <= normalized_headers and "activity_code" not in normalized_headers
    required = {"predecessor", "successor"} if dependency_file else {"activity_code", "description", "planned_start", "planned_finish", "discipline"}
    missing = required - normalized_headers
    if missing: raise HTTPException(400, f"Missing required columns: {', '.join(sorted(missing))}")
    positions = {str(h).strip().lower(): i for i, h in enumerate(headers) if h is not None}
    text_of = lambda value: "" if value is None else str(value).strip()
    errors, inserted, links = [], 0, []
    with closing(connect()) as db:
        db.execute("INSERT OR IGNORE INTO projects(id,name,created_at) VALUES (?,?,?)", (project_id, (project_name or f"Project {project_id}").strip(), now()))
        if project_name and project_name.strip():
            db.execute("UPDATE projects SET name=? WHERE id=?", (project_name.strip(), project_id))
        for number, row in enumerate(records, 2):
            item = {key: row[index] if index < len(row) else None for key, index in positions.items()}
            relationship, lag = text_of(item.get("relationship")), item.get("lag")
            if dependency_file:
                links.append((number, text_of(item["predecessor"]), text_of(item["successor"]), relationship, lag))
                continue
            code = text_of(item["activity_code"])
            discipline = text_of(item["discipline"]).lower()
            start, finish = parse_day(item["planned_start"]), parse_day(item["planned_finish"])
            if discipline not in DISCIPLINES: errors.append({"row": number, "error": f"invalid discipline {discipline}"}); continue
            if not start or not finish or finish < start: errors.append({"row": number, "error": "invalid planned dates"}); continue
            try:
                db.execute("INSERT INTO activities(project_id,activity_code,description,wbs_path,level,discipline,location,planned_start,planned_finish,planned_duration,status,contractor,resource) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (project_id, code, text_of(item["description"]), text_of(item.get("wbs_path")), int(item.get("level") or 6), discipline, text_of(item.get("location")), start.isoformat(), finish.isoformat(), (finish-start).days+1, "not_started", text_of(item.get("contractor")) or None, text_of(item.get("resource")) or None)); inserted += 1
            except sqlite3.IntegrityError as exc:
                errors.append({"row": number, "error": str(exc)}); continue
            for predecessor in re.split(r"[;,]", text_of(item.get("predecessor") or item.get("predecessors"))):
                if predecessor.strip():
                    links.append((number, predecessor.strip(), code, relationship, lag))

        ids = {row["activity_code"]: row["id"] for row in db.execute("SELECT id, activity_code FROM activities WHERE project_id=?", (project_id,))}
        existing = {(row[0], row[1]) for row in db.execute("SELECT predecessor_id, successor_id FROM activity_dependencies WHERE project_id=?", (project_id,))}
        dependencies_inserted = 0
        for number, predecessor, successor, relationship, lag in links:
            relationship = (relationship or "FS").upper()
            try:
                lag_days = float(lag or 0)
            except (TypeError, ValueError):
                errors.append({"row": number, "error": f"invalid lag {lag}"}); continue
            if relationship not in {"FS", "SS", "FF", "SF"}:
                errors.append({"row": number, "error": f"invalid relationship {relationship}"}); continue
            unknown = [c for c in (predecessor, successor) if c not in ids]
            if unknown:
                errors.append({"row": number, "error": f"unknown activity code {', '.join(unknown)}"}); continue
            edge = (ids[predecessor], ids[successor])
            if edge[0] == edge[1] or edge in existing:
                errors.append({"row": number, "error": f"self or duplicate dependency {predecessor} -> {successor}"}); continue
            db.execute("INSERT INTO activity_dependencies(project_id,predecessor_id,successor_id,dependency_type,lag) VALUES (?,?,?,?,?)", (project_id, *edge, relationship, lag_days))
            existing.add(edge); dependencies_inserted += 1
        try:
            cpm_state(db, project_id)  # validate the graph before anything is committed
        except ScheduleCycle as exc:
            db.rollback()
            raise HTTPException(409, f"Import rejected, nothing was saved. {exc}")
        db.commit()
        recompute(db, project_id, "schedule import")
    dependency_columns_present = dependency_file or "predecessor" in normalized_headers or "predecessors" in normalized_headers
    return {"inserted": inserted, "dependencies_inserted": dependencies_inserted, "dependency_columns_present": dependency_columns_present, "dependency_warning": None if dependencies_inserted else "No usable predecessor links were imported; critical-path results use activity durations only.", "errors": errors, "rows": len(records)}
