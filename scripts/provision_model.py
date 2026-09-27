"""Download and materialize the pinned MiniLM model for offline runtime use.

Run once per machine (needs network):  python scripts/provision_model.py
The saved directory is consumed directly by the backend, which then runs fully offline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from sentence_transformers import SentenceTransformer

from backend.app import SEMANTIC_MODEL_NAME, SEMANTIC_MODEL_REVISION

target = Path(__import__("os").environ.get("PROGRESSSYNC_MODEL_PATH", Path(__file__).parents[1] / "ml_artifacts" / "semantic_model"))
model = SentenceTransformer(SEMANTIC_MODEL_NAME, revision=SEMANTIC_MODEL_REVISION)
target.mkdir(parents=True, exist_ok=True)
model.save(str(target))
vector = model.encode("erect line XX102 spool", normalize_embeddings=True)
print(f"provisioned {SEMANTIC_MODEL_NAME}@{SEMANTIC_MODEL_REVISION[:12]} at {target} (dim={len(vector)})")
