"""Reset the demo database to the clean seed state.

Deletes the SQLite file at PROGRESSSYNC_DB (default data/progresssync.db) and re-creates it: schema,
terminology from data/terminology_map.v1.yaml, and the seeded 35-activity demo project.
Stop the backend first. Only files ending in .db are deleted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import backend.app as app_module  # noqa: E402

path = Path(app_module.DB_PATH)
if path.suffix != ".db":
    raise SystemExit(f"Refusing to delete {path}: not a .db file")
for leftover in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
    leftover.unlink(missing_ok=True)
app_module.init_db()
with app_module.connect() as db:
    activities = db.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    terms = db.execute("SELECT COUNT(*) FROM terminology_map").fetchone()[0]
print(f"reset {path}: {activities} seeded activities, {terms} terminology mappings")
