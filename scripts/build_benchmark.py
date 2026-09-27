"""Build the v2 matching benchmark (deterministic: fixed seed, fixed data date).

Writes benchmark/v2/{schedule_project2.csv, schedule_project3.csv, dev.jsonl, held_out.jsonl, MANIFEST.json}.
MANIFEST.json freezes the held-out file by SHA-256; scripts/run_benchmark.py refuses to score a changed
held-out set. Run this ONCE. Re-running would regenerate identical files (same seed), but do not edit cases
to chase metrics.

Cases are hand-written field-language templates per category. They are synthetic and small; results are
NOT production accuracy.
"""
import csv
import hashlib
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parents[1]
OUT = ROOT / "benchmark" / "v2"
DATA_DATE = date(2026, 9, 1)
rng = random.Random(26122)


def day(offset: int) -> str:
    return (DATA_DATE + timedelta(days=offset)).isoformat()


# ---- schedule (project 2) in canonical schedule language --------------------------------------
activities: list[dict] = []


def add(code, description, discipline, location):
    start = rng.randint(-10, 12)
    duration = rng.randint(2, 6)
    activities.append({"activity_code": code, "description": description, "discipline": discipline, "location": location,
                       "planned_start": day(start), "planned_finish": day(start + duration - 1), "level": 6})


LINES = list(range(2101, 2113))
RACK = {line: 1 + i % 3 for i, line in enumerate(LINES)}
for line in LINES:
    add(f"PIP-{line}", f"Erect piping segment line {line} at R{RACK[line]:02d}", "piping", f"R{RACK[line]:02d}")
    add(f"PTS-{line}", f"Pressure test line {line}", "piping", f"R{RACK[line]:02d}")
for line in LINES[:6]:
    add(f"BLT-{line}", f"Flange bolting line {line}", "piping", f"R{RACK[line]:02d}")
PUMPS = [f"P-30{k}" for k in range(1, 7)]
for p in PUMPS:
    add(f"CIV-F{p[2:]}", f"Pour foundation for pump {p}", "civil", "Unit 3")
    add(f"ROT-I{p[2:]}", f"Install pump {p}", "rotating_equipment", "Unit 3")
    add(f"ROT-A{p[2:]}", f"Align pump {p}", "rotating_equipment", "Unit 3")
add("ROT-CT103", "Install pump CT-103", "rotating_equipment", "Unit 2")
add("ROT-K401", "Align compressor K-401", "rotating_equipment", "Unit 2")
VESSELS = [f"V-20{k}" for k in range(1, 6)]
for v in VESSELS:
    add(f"STA-{v}", f"Erect vessel {v}", "static_equipment", "Unit 2")
for k in range(1, 4):
    add(f"STA-E10{k}", f"Set heat exchanger E-10{k}", "static_equipment", "Unit 2")
for area in ("North", "South", "East"):
    add(f"CIV-T{area[0]}", f"Excavate trench area {area}", "civil", f"Area {area}")
    add(f"HSE-{area[0]}", f"Permit and safety inspection area {area}", "hse", f"Area {area}")
FEEDERS = [f"F-1{k}" for k in range(1, 7)]
for i, f in enumerate(FEEDERS):
    add(f"ELE-{f}", f"Cable installation feeder {f} to MCC-{1 + i % 2}", "electrical", "Substation")
for r in (1, 2, 3):
    add(f"ELE-TR{r}", f"Install cable tray at R0{r}", "electrical", f"R0{r}")
TRANSMITTERS = [f"PT-10{k}" for k in range(1, 7)]
for t in TRANSMITTERS:
    add(f"INS-{t}", f"Calibrate pressure transmitter {t}", "instrumentation", "Unit 2")
for k in range(1, 4):
    add(f"INS-LC{k}", f"Loop check FT-20{k}", "instrumentation", "Unit 2")

by_code = {a["activity_code"]: a for a in activities}
# Project 3 is a sister unit with look-alike activities; reports go to project 2 and must never match these.
distractors = [{**a, "activity_code": "Z" + a["activity_code"]} for a in activities if a["activity_code"].startswith(("PIP", "ROT-I", "INS"))]

# ---- cases ------------------------------------------------------------------------------------
cases: list[dict] = []


def case(category, text, truth, ambiguous=False):
    cases.append({"category": category, "text": text, "truth": truth, "ambiguous": ambiguous})


pct = lambda: rng.choice([20, 30, 40, 50, 60, 70, 80, 100])
for _ in range(14):
    line, p, t, v = rng.choice(LINES), rng.choice(PUMPS), rng.choice(TRANSMITTERS), rng.choice(VESSELS)
    kind = rng.randrange(4)
    if kind == 0: case("exact", f"Erect piping segment line {line} at R{RACK[line]:02d}, {pct()}%.", f"PIP-{line}")
    elif kind == 1: case("exact", f"Pressure test line {line} done, 100%.", f"PTS-{line}")
    elif kind == 2: case("exact", f"Calibrate pressure transmitter {t} finished, 100%.", f"INS-{t}")
    else: case("exact", f"Install pump {p}, {pct()}%.", f"ROT-I{p[2:]}")
for _ in range(14):
    line, p, t, v = rng.choice(LINES), rng.choice(PUMPS), rng.choice(TRANSMITTERS), rng.choice(VESSELS)
    kind = rng.randrange(4)
    if kind == 0: case("synonym", f"Crew put up the pipe for line {line} on rack {RACK[line]}, {pct()}%.", f"PIP-{line}")
    elif kind == 1: case("synonym", f"Transmitter {t} has been checked and set against the reference gauge, 100%.", f"INS-{t}")
    elif kind == 2: case("synonym", f"Vessel {v} lifted into position by the crane team, {pct()}%.", f"STA-{v}")
    else: case("synonym", f"Pump {p} shaft lined up with the motor, {pct()}%.", f"ROT-A{p[2:]}")
for _ in range(14):
    line, p, t = rng.choice(LINES), rng.choice(PUMPS), rng.choice(TRANSMITTERS)
    kind = rng.randrange(3)
    if kind == 0: case("abbreviation", f"Ln {line} pip seg erctd R0{RACK[line]} {pct()}%", f"PIP-{line}")
    elif kind == 1: case("abbreviation", f"{t.replace('-', '')} calib done 100%", f"INS-{t}")
    else: case("abbreviation", f"Inst pmp {p.replace('-', '')} {pct()}%", f"ROT-I{p[2:]}")
for _ in range(14):
    line, p, t, v = rng.choice(LINES), rng.choice(PUMPS), rng.choice(TRANSMITTERS), rng.choice(VESSELS)
    kind = rng.randrange(4)
    if kind == 0: case("typo_ocr", f"Calibrate presure transmiter {t.replace('0', 'O')}, {pct()}%.", f"INS-{t}")
    elif kind == 1: case("typo_ocr", f"Erect pipng segmnt line {str(line).replace('0', 'O')} at R0{RACK[line]}, {pct()}%.", f"PIP-{line}")
    elif kind == 2: case("typo_ocr", f"Instal pumpp {p.replace('0', 'O')}, {pct()}%.", f"ROT-I{p[2:]}")
    else: case("typo_ocr", f"Erect vesel {v.replace('0', 'O')}, {pct()}%.", f"STA-{v}")
for _ in range(14):
    line, p = rng.choice(LINES), rng.choice(PUMPS)
    kind = rng.randrange(3)
    if kind == 0: case("near_duplicate", f"Piping segment erected at rack {RACK[line]}, {pct()}%.", f"PIP-{line}", ambiguous=True)
    elif kind == 1: case("near_duplicate", f"Pump alignment done in Unit 3, 100%.", f"ROT-A{p[2:]}", ambiguous=True)
    else: case("near_duplicate", f"Pressure test on line {str(line)[:3]}, 100%.", f"PTS-{line}", ambiguous=True)
UNKNOWN = [
    "Scaffolding at flare stack FS-900 dismantled, 100%.",
    "Unknown work package ZZ-{n} at jetty, 20%.",
    "Painting of storage tank TK-800 roof, 30%.",
    "Fireproofing of pipe rack columns in area West, 50%.",
    "Insulation of steam tracing on line 9905, 40%.",
    "Fence erection around laydown yard, 60%.",
    "Unknown package pressure test at Area 9, 20%.",
]
for i in range(14):
    case("unknown", rng.choice(UNKNOWN).format(n=100 + i), None)
for _ in range(14):
    line, t, v = rng.choice(LINES), rng.choice(TRANSMITTERS), rng.choice(VESSELS)
    kind = rng.randrange(3)
    if kind == 0: case("missing_timestamp", f"Line {line} piping segment erected at R0{RACK[line]}, {pct()}%.", f"PIP-{line}")
    elif kind == 1: case("missing_timestamp", f"Vessel {v} erected, {pct()}%.", f"STA-{v}")
    else: case("missing_timestamp", f"Transmitter {t} calibrated, 100%.", f"INS-{t}")
for _ in range(14):
    t, p, v = rng.choice(TRANSMITTERS), rng.choice(PUMPS), rng.choice(VESSELS)
    kind = rng.randrange(3)
    if kind == 0: case("wrong_discipline", f"Piping crew calibrated transmitter {t}, 100%.", f"INS-{t}", ambiguous=True)
    elif kind == 1: case("wrong_discipline", f"Electrical crew installed pump {p} at 14:30, {pct()}%.", f"ROT-I{p[2:]}", ambiguous=True)
    else: case("wrong_discipline", f"Civil crew erected vessel {v}, {pct()}%.", f"STA-{v}", ambiguous=True)
for _ in range(14):
    line = rng.choice(LINES)
    kind = rng.randrange(3)
    if kind == 0: case("granularity", f"All piping on rack {RACK[line]} package complete, 100%.", None, ambiguous=True)
    elif kind == 1: case("granularity", "Pump area mechanical works in Unit 3, 60%.", None, ambiguous=True)
    else: case("granularity", "Instrumentation calibration package 50% complete.", None, ambiguous=True)
for _ in range(14):
    line, f = rng.choice(LINES[:6]), rng.choice(FEEDERS)
    rack3 = [l for l in LINES if RACK[l] == 3]
    kind = rng.randrange(4)
    if kind == 0: case("terminology", f"Hydrotest line {line} passed, 100%.", f"PTS-{line}")
    elif kind == 1: case("terminology", f"Boltup line {line} done @ 16:00, 100%.", f"BLT-{line}")
    elif kind == 2: case("terminology", f"Cable pull feeder {f} {pct()}%.", f"ELE-{f}")
    else:
        l3 = rng.choice(rack3)
        case("terminology", f"Spool line {l3} erected on rack 3, {pct()}%.", f"PIP-{l3}")

for i, c in enumerate(cases):
    c["id"] = f"c{i:03d}"
rng.shuffle(cases)
dev = cases[: int(len(cases) * 0.4)]
held_out = cases[int(len(cases) * 0.4):]

# ---- write --------------------------------------------------------------------------------------
OUT.mkdir(parents=True, exist_ok=True)
fields = ["activity_code", "description", "wbs_path", "level", "discipline", "location", "planned_start", "planned_finish"]
for name, rows in (("schedule_project2.csv", activities), ("schedule_project3.csv", distractors)):
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({**r, "wbs_path": f"BENCH/{r['discipline'].upper()}/{r['location']}"} for r in rows)
for name, rows in (("dev.jsonl", dev), ("held_out.jsonl", held_out)):
    (OUT / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
manifest = {
    "data_date": DATA_DATE.isoformat(), "seed": 26122, "project_id": 2, "distractor_project_id": 3,
    "activities": len(activities), "distractor_activities": len(distractors), "dev_cases": len(dev), "held_out_cases": len(held_out),
    "sha256": {n: hashlib.sha256((OUT / n).read_bytes()).hexdigest() for n in ("schedule_project2.csv", "schedule_project3.csv", "dev.jsonl", "held_out.jsonl")},
}
(OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: v for k, v in manifest.items() if k != "sha256"}))
