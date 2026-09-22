import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from fastapi.testclient import TestClient
from backend.app import app

with TestClient(app) as client:
    print('critical path:', len(client.get('/api/v1/projects/1/critical-path').json()))
    response = client.post('/api/v1/reports', json={'text':'Piping crew completed spool XX102 at rack 3, 100%.','source':'demo'})
    print('report:', response.json()['match'], response.json()['latency_ms'], 'ms')
    print('candidates:', len(client.get(f"/api/v1/events/{response.json()['event_id']}/candidates").json()))
    print('review queue:', len(client.get('/api/v1/review-queue').json()))
    client.post(f"/api/v1/events/{response.json()['event_id']}/confirm", json={'actor':'demo-planner'})
    print('audit rows:', len(client.get('/api/v1/audit').json()))
    print('agent:', client.post('/api/v1/agent/message', json={'text':'Pump CT103 installed at Unit 2, 50%.'}).json()['reply'])
