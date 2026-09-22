# Offline demo

1. Start `uvicorn backend.app:app` with `DEMO_MODE=true`.
2. In Ingest, load the high-confidence example and process it.
3. Open Review queue to inspect candidate bars, source span, terminology mapping, and margin.
4. Process the ambiguous example and approve/reassign it.
5. Open Schedule to see actuals and critical activities, then Analytics and Audit + memory.
6. Send `Pump CT103 installed at Unit 2, 50%.` through Time Agent. It calls the same `/reports` pipeline.
7. Submit `ZZ-999 unknown activity at offshore platform, 20%.` and verify it remains in the queue.

The browser voice button uses Web Speech when available and displays a typed fallback when it is not.
