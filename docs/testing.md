# Testing

`pytest -q` exercises report ingestion, extraction, candidate evidence, review confirmation, audit writes, Time Agent reuse, CPM availability, and malformed file errors.

The benchmark generator creates 280 activities over all seven disciplines and 60 reports with terminology substitutions, OCR-like noise, missing IDs, near duplicates, and unmatched cases. Fifteen percent is placed in a separate held-out file. `scripts/run_benchmark.py` prints measured auto-match precision, silent errors, routing rates, Recall@5, and latency.

The test database is isolated through `PROGRESSSYNC_DB`. No benchmark metric is stored as a claim in source; run output is authoritative.
