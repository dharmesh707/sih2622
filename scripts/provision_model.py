"""One-time download of the pinned MiniLM model into the local Hugging Face cache.

Run once per machine (needs network):  python scripts/provision_model.py
After this, the backend and tests run fully offline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from sentence_transformers import SentenceTransformer

from backend.app import SEMANTIC_MODEL_NAME, SEMANTIC_MODEL_REVISION

model = SentenceTransformer(SEMANTIC_MODEL_NAME, revision=SEMANTIC_MODEL_REVISION)
vector = model.encode("erect line XX102 spool", normalize_embeddings=True)
print(f"provisioned {SEMANTIC_MODEL_NAME}@{SEMANTIC_MODEL_REVISION[:12]} (dim={len(vector)})")
