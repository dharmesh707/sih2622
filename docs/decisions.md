# Decisions

The fixed fusion design is `0.30 ID + 0.15 lexical + 0.25 semantic + 0.30 context`, multiplied by a temporal compatibility factor. These weights are design parameters, not accuracy claims.

Decisioning uses both score and separation: auto-match requires top >= 0.82 and margin >= 0.12; top >= 0.45 routes to review; otherwise the event remains unmatched. This makes near-duplicate activities visible instead of silently selecting a plausible wrong activity.

The semantic score is a deterministic proxy in the offline MVP. A sentence-transformer can be added behind the same scorer interface when a local model is available. The LLM is not required for structured output or schedule writes.
