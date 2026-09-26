# Decisions

The fixed fusion design is `0.30 ID + 0.15 lexical + 0.25 semantic + 0.30 context`, multiplied by a temporal compatibility factor. These weights are design parameters, not accuracy claims.

Decisioning uses both score and separation: auto-match requires top >= 0.82 and margin >= 0.12; top >= 0.45 routes to review; otherwise the event remains unmatched. This makes near-duplicate activities visible instead of silently selecting a plausible wrong activity.

The semantic score comes from the pinned local `sentence-transformers/all-MiniLM-L6-v2` model (provisioned once with `scripts/provision_model.py`). There is no proxy fallback: if the model is missing, the API returns 503 instead of scoring with a weaker signal. No LLM is used for structured output or schedule writes.
