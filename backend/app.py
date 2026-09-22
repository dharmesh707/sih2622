from __future__ import annotations

import csv
import io
import json
import math
import os
import pickle
import re
import sqlite3
import time
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from sentence_transformers import SentenceTransformer

import networkx as nx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("PROGRESSSYNC_DB", ROOT / "data" / "progresssync.db"))
TERM_PATH = ROOT / "data" / "terminology_map.v1.yaml"
FRONTEND = ROOT / "frontend"
DISCIPLINES = {"civil", "piping", "static_equipment", "rotating_equipment", "electrical", "instrumentation", "hse"}
SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"
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
            norm(identifier) in norm(activity["activity_code"])
            or norm(identifier) in norm(activity["description"])
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
        _semantic_model = SentenceTransformer(
            SEMANTIC_MODEL_NAME,
            local_files_only=True,
        )

    return _semantic_model


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
 status TEXT DEFAULT 'not_started', contractor TEXT, resource TEXT, embedding TEXT DEFAULT '[]', at_risk INTEGER DEFAULT 0,
 UNIQUE(project_id, activity_code)
);
CREATE TABLE IF NOT EXISTS activity_dependencies (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, predecessor_id INTEGER NOT NULL, successor_id INTEGER NOT NULL, dependency_type TEXT DEFAULT 'FS', lag REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS cpm_state (activity_id INTEGER PRIMARY KEY, early_start TEXT, early_finish TEXT, late_start TEXT, late_finish TEXT, total_float REAL, critical INTEGER, project_finish TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS schedule_snapshots (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, reason TEXT, created_at TEXT NOT NULL, project_finish TEXT, state_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS field_reports (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, source TEXT NOT NULL, raw_text TEXT NOT NULL, submitted_at TEXT NOT NULL, latency_ms REAL, status TEXT DEFAULT 'received');
CREATE TABLE IF NOT EXISTS execution_events (id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL, event_type TEXT, discipline TEXT, activity_terms TEXT, identifiers TEXT, location_terms TEXT, quantity REAL, unit TEXT, progress REAL, event_timestamp TEXT, source_text TEXT, source_span TEXT, extraction_confidence REAL, status TEXT DEFAULT 'PENDING');
CREATE TABLE IF NOT EXISTS match_candidates (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, activity_id INTEGER NOT NULL, score_id REAL, score_lexical REAL, score_semantic REAL, score_context REAL, temporal_factor REAL, fused_score REAL, rank INTEGER, evidence_json TEXT);
CREATE TABLE IF NOT EXISTS match_decisions (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, decision TEXT NOT NULL, activity_id INTEGER, top_score REAL, second_score REAL, margin REAL, actor TEXT, comment TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS terminology_map (id INTEGER PRIMARY KEY, field_term TEXT, canonical_term TEXT, discipline TEXT, version TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS delay_causes (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, cause TEXT, notes TEXT);
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, activity_id INTEGER, event_id INTEGER, old_value TEXT, new_value TEXT, source TEXT, evidence TEXT, score REAL, actor TEXT, approval_status TEXT, created_at TEXT NOT NULL);
"""


def now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with closing(connect()) as db:
        db.executescript(SCHEMA)
        db.commit()
        if not db.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
            db.execute("INSERT INTO projects(name, created_at) VALUES (?, ?)", ("OIL Demo Project", now()))
            load_terms(db)
            seed_schedule(db)
            recompute(db, 1, "initial baseline")


def load_terms(db: sqlite3.Connection) -> None:
    terms = [("spool", "piping segment", "piping"), ("install", "erect", "civil"), ("erection", "erect", "static_equipment"), ("rack 3", "R03", "piping"), ("rack-3", "R03", "piping"), ("CT103", "CT-103", "rotating_equipment"), ("pump", "pump", "rotating_equipment"), ("boltup", "bolting", "piping"), ("hydrotest", "pressure test", "piping"), ("cable pull", "cable installation", "electrical")]
    db.executemany("INSERT INTO terminology_map(field_term, canonical_term, discipline, version, source) VALUES (?, ?, ?, 'v1', 'OIL field lexicon')", terms)


def seed_schedule(db: sqlite3.Connection) -> None:
    rows = []
    base = date.today() - timedelta(days=12)
    templates = [
        ("CIV", "Foundation and concrete works", "civil", "Area A"),
        ("PIP", "Erect line XX102 spool", "piping", "R03"),
        ("STA", "Erect vessel V-201", "static_equipment", "Unit 2"),
        ("ROT", "Install pump CT-103", "rotating_equipment", "Unit 2"),
        ("ELE", "Install cable tray", "electrical", "R03"),
        ("INS", "Calibrate pressure transmitter", "instrumentation", "Unit 2"),
        ("HSE", "Permit and safety inspection", "hse", "Site"),
    ]
    for i in range(35):
        prefix, desc, discipline, location = templates[i % len(templates)]
        code = f"{prefix}-L5-{i+1:03d}"
        if discipline == "piping":
            desc = f"Erect line XX{102 + i // 7:03d} spool"
        start = base + timedelta(days=i % 9)
        finish = start + timedelta(days=2 + i % 4)
        rows.append((1, code, f"{desc} {i+1:03d}", f"{discipline.upper()} / {location} / PACKAGE {i//7+1}", 5 if i % 4 else 6, discipline, location, start.isoformat(), finish.isoformat(), (finish-start).days + 1, 0, "not_started"))
    db.executemany("INSERT INTO activities(project_id,activity_code,description,wbs_path,level,discipline,location,planned_start,planned_finish,planned_duration,percent_complete,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    activities = db.execute("SELECT id FROM activities WHERE project_id=1 ORDER BY id").fetchall()
    edges = [(1, activities[i-1][0], activities[i][0], "FS", 0) for i in range(1, len(activities))]
    db.executemany("INSERT INTO activity_dependencies(project_id,predecessor_id,successor_id,dependency_type,lag) VALUES (?,?,?,?,?)", edges)


def parse_day(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"([a-z])([0-9])", r"\1 \2", text)
    text = text.replace("1o", "10").replace("o", "0")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    return set(norm(text).split())


def extract_event(text: str, source: str, report_id: int) -> dict[str, Any]:
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

    # Detect equipment/activity identifiers.
    equipment = re.findall(
        r"\b(?:[A-Z]{2,5}[- ]?\d{2,4}|[A-Z]{1,3}\d{3,4})\b",
        clean,
    )

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
    event_timestamp = date.today().isoformat()

    return {
        "report_id": report_id,
        "event_type": "progress_update",
        "discipline": discipline,
        "activity_terms": activity_terms,
        "identifiers": equipment,
        "location_terms": location,
        "quantity": float(quantity_match.group(1)) if quantity_match else None,
        "unit": quantity_match.group(2) if quantity_match else None,
        "progress": (
            float(progress_match.group(1))
            if progress_match
            else (
                100.0
                if any(
                    word in normalized
                    for word in ("complete", "completed", "finished")
                )
                else None
            )
        ),
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
    if any(
        norm(identifier) in activity_code
        or norm(identifier) in description
        for identifier in event["identifiers"]
    ):
        score_id = 1.0
    elif any(
        part in field
        for part in activity_code.split()
        if len(part) > 2
    ):
        score_id = 0.82

    # 2. Field terminology mapping.
    mapped = []
    mapped_field = field
    for term in terms:
        if term["field_term"] in mapped_field:
            mapped.append(dict(term))
            mapped_field = mapped_field.replace(
                term["field_term"],
                term["canonical_term"],
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


def make_match(db: sqlite3.Connection, event_id: int, event: dict[str, Any]) -> dict[str, Any]:
    activities = db.execute(
        "SELECT * FROM activities WHERE project_id=1 ORDER BY id"
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

        candidates.append({
            "scores": scores,
            "evidence": evidence,
            "activity": activity,
        })

    if not candidates:
        candidates = [
            {
                "scores": score_candidate(event, event, terms)[0],
                "evidence": {},
                "activity": event,
            }
        ]

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

    activity_id = (
        top_activity_id
        if decision != "UNMATCHED"
        else None
    )

    db.execute(
        "INSERT INTO match_decisions("
        "event_id,decision,activity_id,top_score,second_score,margin,actor,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            event_id,
            decision,
            activity_id,
            top_score_for_decision,
            second_score_for_decision,
            margin_for_decision,
            "system",
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


def cpm_state(db: sqlite3.Connection, project_id: int) -> dict[int, dict[str, Any]]:
    acts = db.execute("SELECT * FROM activities WHERE project_id=?", (project_id,)).fetchall()
    edges = db.execute("SELECT predecessor_id, successor_id, lag FROM activity_dependencies WHERE project_id=?", (project_id,)).fetchall()
    graph = nx.DiGraph()
    graph.add_nodes_from(a["id"] for a in acts)
    graph.add_edges_from((e["predecessor_id"], e["successor_id"], {"lag": e["lag"]}) for e in edges)
    if not nx.is_directed_acyclic_graph(graph):
        raise ValueError("Dependency graph contains a cycle")
    by_id = {a["id"]: a for a in acts}
    es: dict[int, float] = {}
    ef: dict[int, float] = {}
    for node in nx.topological_sort(graph):
        duration = float(by_id[node]["planned_duration"] or 1)
        es[node] = max((ef[p] + float(graph[p][node].get("lag", 0)) for p in graph.predecessors(node)), default=0)
        ef[node] = es[node] + duration
    project_finish = max(ef.values(), default=0)
    ls: dict[int, float] = {}
    lf: dict[int, float] = {}
    for node in reversed(list(nx.topological_sort(graph))):
        duration = float(by_id[node]["planned_duration"] or 1)
        lf[node] = min((ls[s] - float(graph[node][s].get("lag", 0)) for s in graph.successors(node)), default=project_finish)
        ls[node] = lf[node] - duration
    result = {}
    for node in graph.nodes:
        result[node] = {"early_start": es[node], "early_finish": ef[node], "late_start": ls[node], "late_finish": lf[node], "total_float": round(ls[node]-es[node], 2), "critical": abs(ls[node]-es[node]) < 0.001, "project_finish": project_finish}
    return result


def recompute(db: sqlite3.Connection, project_id: int, reason: str) -> dict[str, Any]:
    state = cpm_state(db, project_id)
    serialized = json.dumps(state)
    finish = max((v["project_finish"] for v in state.values()), default=0)
    db.execute("INSERT INTO schedule_snapshots(project_id,reason,created_at,project_finish,state_json) VALUES (?,?,?,?,?)", (project_id, reason, now(), finish, serialized))
    for activity_id, values in state.items():
        db.execute("INSERT OR REPLACE INTO cpm_state(activity_id,early_start,early_finish,late_start,late_finish,total_float,critical,project_finish,updated_at) VALUES (?,?,?,?,?,?,?,?,?)", (activity_id, values["early_start"], values["early_finish"], values["late_start"], values["late_finish"], values["total_float"], int(values["critical"]), finish, now()))
    db.commit()
    return {"project_finish": finish, "critical": [k for k, v in state.items() if v["critical"]], "state": state}


def apply_update(db: sqlite3.Connection, project_id: int, event_id: int, activity_id: int, actor: str, comment: str = "") -> dict[str, Any]:
    event = db.execute("SELECT * FROM execution_events WHERE id=?", (event_id,)).fetchone()
    decision = db.execute("SELECT * FROM match_decisions WHERE event_id=? ORDER BY id DESC LIMIT 1", (event_id,)).fetchone()
    activity = db.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
    before = recompute(db, project_id, "pre-update snapshot")
    old = {"percent_complete": activity["percent_complete"], "actual_start": activity["actual_start"], "actual_finish": activity["actual_finish"], "status": activity["status"]}
    progress = event["progress"] if event["progress"] is not None else old["percent_complete"]
    status = "complete" if progress >= 100 else "in_progress" if progress > 0 else old["status"]
    actual_start = old["actual_start"] or event["event_timestamp"] if progress > 0 else old["actual_start"]
    actual_finish = event["event_timestamp"] if progress >= 100 else old["actual_finish"]
    new = {"percent_complete": progress, "actual_start": actual_start, "actual_finish": actual_finish, "status": status}
    db.execute("UPDATE activities SET percent_complete=?,actual_start=?,actual_finish=?,status=? WHERE id=?", (progress, actual_start, actual_finish, status, activity_id))
    db.execute("UPDATE match_decisions SET decision=?,activity_id=?,actor=?,comment=? WHERE id=?", ("APPROVED", activity_id, actor, comment, decision["id"]))
    db.execute("INSERT INTO audit_log(project_id,activity_id,event_id,old_value,new_value,source,evidence,score,actor,approval_status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (project_id, activity_id, event_id, json.dumps(old), json.dumps(new), "field_report", event["source_text"], decision["top_score"] if decision else None, actor, "approved", now()))
    after = recompute(db, project_id, "confirmed actual update")
    db.commit()
    return {"old": old, "new": new, "before": before, "after": after, "critical_path_changed": before["critical"] != after["critical"]}


class ReportIn(BaseModel):
    project_id: int = 1
    text: str = Field(min_length=1, max_length=20000)
    source: str = "text"


class DecisionIn(BaseModel):
    activity_id: int | None = None
    actor: str = "planner"
    comment: str = ""


class AgentIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    session_id: str | None = None


app = FastAPI(title="ProgressSync AI", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup() -> None:
    init_db()

@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")

@app.get("/app.js")
def js() -> FileResponse:
    return FileResponse(FRONTEND / "app.js")

@app.get("/styles.css")
def css() -> FileResponse:
    return FileResponse(FRONTEND / "styles.css")

@app.get("/api/v1/projects/{project_id}/activities")
def activities(project_id: int):
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT a.*, c.total_float, c.critical FROM activities a LEFT JOIN cpm_state c ON a.id=c.activity_id WHERE a.project_id=? ORDER BY a.id", (project_id,))]

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
        report_id = db.execute("INSERT INTO field_reports(project_id,source,raw_text,submitted_at) VALUES (?,?,?,?)", (payload.project_id, payload.source, payload.text, now())).lastrowid
        event = extract_event(payload.text, payload.source, report_id)
        event_id = db.execute("INSERT INTO execution_events(report_id,event_type,discipline,activity_terms,identifiers,location_terms,quantity,unit,progress,event_timestamp,source_text,source_span,extraction_confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (report_id, event["event_type"], event["discipline"], event["activity_terms"], json.dumps(event["identifiers"]), event["location_terms"], event["quantity"], event["unit"], event["progress"], event["event_timestamp"], event["source_text"], json.dumps(event["source_span"]), event["extraction_confidence"])).lastrowid
        event["id"] = event_id
        match = make_match(db, event_id, event)
        latency = round((time.perf_counter() - started) * 1000, 2)
        db.execute("UPDATE field_reports SET latency_ms=?,status=? WHERE id=?", (latency, match["decision"], report_id))
        db.commit()
        return {"report_id": report_id, "event_id": event_id, "event": event, "match": match, "latency_ms": latency}

@app.get("/api/v1/events/{event_id}")
def event(event_id: int):
    with closing(connect()) as db:
        row = db.execute("SELECT * FROM execution_events WHERE id=?", (event_id,)).fetchone()
        if not row: raise HTTPException(404, "Event not found")
        data = dict(row); data["identifiers"] = json.loads(data["identifiers"] or "[]"); data["source_span"] = json.loads(data["source_span"] or "[]")
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
def review_queue():
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT e.*, d.decision, d.top_score, d.second_score, d.margin, d.activity_id FROM execution_events e JOIN match_decisions d ON d.event_id=e.id WHERE d.decision IN ('REVIEW_REQUIRED','UNMATCHED') ORDER BY e.id DESC")]

@app.post("/api/v1/events/{event_id}/confirm")
def confirm(event_id: int, payload: DecisionIn):
    with closing(connect()) as db:
        decision = db.execute(
            "SELECT * FROM match_decisions WHERE event_id=? ORDER BY id DESC LIMIT 1",
            (event_id,)
        ).fetchone()

        if not decision:
            raise HTTPException(404, "Match decision not found")

        if decision["decision"] == "APPROVED":
            raise HTTPException(409, "Event has already been confirmed")

        activity_id = payload.activity_id or decision["activity_id"]

        if not activity_id:
            raise HTTPException(
                400,
                "activity_id is required for an unmatched event"
            )

        return apply_update(
            db,
            1,
            event_id,
            activity_id,
            payload.actor,
            payload.comment
        )

@app.post("/api/v1/events/{event_id}/reject")
def reject(event_id: int, payload: DecisionIn):
    with closing(connect()) as db:
        db.execute("UPDATE match_decisions SET decision='REJECTED',actor=?,comment=? WHERE event_id=?", (payload.actor, payload.comment, event_id)); db.execute("UPDATE execution_events SET status='REJECTED' WHERE id=?", (event_id,)); db.commit(); return {"event_id": event_id, "decision": "REJECTED"}

@app.post("/api/v1/projects/{project_id}/recompute")
def recompute_api(project_id: int):
    with closing(connect()) as db: return recompute(db, project_id, "manual recompute")

@app.get("/api/v1/projects/{project_id}/critical-path")
def critical_path(project_id: int):
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT a.*, c.total_float, c.critical FROM activities a JOIN cpm_state c ON a.id=c.activity_id WHERE a.project_id=? AND c.critical=1 ORDER BY c.early_start", (project_id,))]

@app.get("/api/v1/projects/{project_id}/snapshots/{snapshot_id}/diff")
def snapshot_diff(project_id: int, snapshot_id: int):
    with closing(connect()) as db:
        current = db.execute("SELECT * FROM schedule_snapshots WHERE project_id=? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        old = db.execute("SELECT * FROM schedule_snapshots WHERE project_id=? AND id=?", (project_id, snapshot_id)).fetchone()
        if not old or not current: raise HTTPException(404, "Snapshot not found")
        before, after = json.loads(old["state_json"]), json.loads(current["state_json"])
        return {"from": old["id"], "to": current["id"], "project_finish_change": current["project_finish"] - old["project_finish"], "critical_entered": [k for k in after if after[k]["critical"] and not before.get(k, {}).get("critical")], "critical_left": [k for k in before if before[k]["critical"] and not after.get(k, {}).get("critical")], "float_warnings": [k for k, value in after.items() if value["total_float"] <= 1]}

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

    return {
        "semantic_model": SEMANTIC_MODEL_NAME,
        "reranker_enabled": RERANKER_ENABLED,
        "reranker_artifact_exists": artifact_exists,
        "reranker_version": artifact_version,
        "reranker_auto_threshold": RERANKER_AUTO_THRESHOLD,
        "reranker_margin_threshold": RERANKER_MARGIN_THRESHOLD,
    }


@app.get("/api/v1/analytics/discipline-productivity")
def productivity():
    with closing(connect()) as db:
        return [dict(row) for row in db.execute("SELECT discipline, COUNT(*) activities, ROUND(AVG(percent_complete),1) progress, ROUND(AVG(CASE WHEN actual_finish IS NOT NULL THEN planned_duration END),1) actual_duration FROM activities GROUP BY discipline ORDER BY discipline")]

@app.get("/api/v1/analytics/delay-causes")
def delay_causes():
    with closing(connect()) as db: return [dict(row) for row in db.execute("SELECT cause, COUNT(*) count FROM delay_causes GROUP BY cause ORDER BY count DESC")]

@app.get("/api/v1/analytics/variance")
def variance():
    with closing(connect()) as db: return [dict(row) for row in db.execute("SELECT wbs_path, ROUND(AVG(percent_complete),1) progress, COUNT(*) activities FROM activities GROUP BY wbs_path ORDER BY wbs_path")]

@app.get("/api/v1/memory/similar")
def memory(description: str = "piping erection"):
    with closing(connect()) as db:
        rows = db.execute("SELECT * FROM activities WHERE actual_finish IS NOT NULL ORDER BY percent_complete DESC").fetchall()
        return [{"activity_code": r["activity_code"], "description": r["description"], "discipline": r["discipline"], "actual_duration": r["planned_duration"], "planned_duration": r["planned_duration"], "similarity": similarity(description, r["description"])} for r in rows[:10]]

@app.get("/api/v1/audit")
def audit():
    with closing(connect()) as db: return [dict(row) for row in db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100")]

@app.get("/api/v1/terminology-map")
def terminology():
    with closing(connect()) as db: return [dict(row) for row in db.execute("SELECT * FROM terminology_map ORDER BY field_term")]

@app.post("/api/v1/agent/message")
def agent(payload: AgentIn):
    result = report(ReportIn(text=payload.text, source="time_agent"))
    decision = result["match"]["decision"]
    reply = "I found a confident schedule activity. Please confirm." if decision == "AUTO_MATCHED" else "I found multiple plausible activities. Please review the evidence." if decision == "REVIEW_REQUIRED" else "I could not find a schedule counterpart, so I preserved the observation for review."
    result["reply"] = reply
    return result

@app.post("/api/v1/projects/{project_id}/schedule/import")
async def import_schedule(project_id: int, file: UploadFile = File(...)):
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
    required = {"activity_code", "description", "planned_start", "planned_finish", "discipline"}
    normalized_headers = {str(h).strip().lower() for h in headers if h is not None}
    missing = required - normalized_headers
    if missing: raise HTTPException(400, f"Missing required columns: {', '.join(sorted(missing))}")
    positions = {str(h).strip().lower(): i for i, h in enumerate(headers)}
    errors, inserted = [], 0
    with closing(connect()) as db:
        for number, row in enumerate(records, 2):
            item = {key: row[index] if index < len(row) else "" for key, index in positions.items()}
            discipline = str(item["discipline"]).strip().lower()
            start, finish = parse_day(item["planned_start"]), parse_day(item["planned_finish"])
            if discipline not in DISCIPLINES: errors.append({"row": number, "error": f"invalid discipline {discipline}"}); continue
            if not start or not finish or finish < start: errors.append({"row": number, "error": "invalid planned dates"}); continue
            try:
                db.execute("INSERT INTO activities(project_id,activity_code,description,wbs_path,level,discipline,location,planned_start,planned_finish,planned_duration,status) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (project_id, item["activity_code"], item["description"], item.get("wbs_path", ""), int(item.get("level") or 6), discipline, item.get("location", ""), start.isoformat(), finish.isoformat(), (finish-start).days+1, "not_started")); inserted += 1
            except sqlite3.IntegrityError as exc: errors.append({"row": number, "error": str(exc)})
        db.commit()
        recompute(db, project_id, "schedule import")
    return {"inserted": inserted, "errors": errors, "rows": len(records)}
