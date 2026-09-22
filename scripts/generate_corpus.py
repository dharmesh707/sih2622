import csv, json, random
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).parents[1]
OUT = ROOT / 'benchmark' / 'generated'
OUT.mkdir(parents=True, exist_ok=True)
random.seed(26122)
disciplines = [('civil','Area A','Foundation'),('piping','R03','Erect line'),('static_equipment','Unit 2','Erect vessel'),('rotating_equipment','Unit 2','Install pump'),('electrical','R03','Install cable tray'),('instrumentation','Unit 2','Calibrate transmitter'),('hse','Site','Safety inspection')]
rows=[]
for index in range(280):
    discipline, location, verb = disciplines[index % len(disciplines)]
    code = f'{discipline[:3].upper()}-L6-{index+1:03d}'
    start = date.today() + timedelta(days=index % 20)
    finish = start + timedelta(days=2 + index % 5)
    rows.append({'activity_code':code,'description':f'{verb} {index+1:03d}','wbs_path':f'{discipline.upper()}/{location}/PACKAGE {index//14+1}','level':6,'discipline':discipline,'location':location,'planned_start':start.isoformat(),'planned_finish':finish.isoformat()})
with (OUT/'schedule.csv').open('w', newline='', encoding='utf-8') as handle:
    writer=csv.DictWriter(handle, fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)
reports=[]
for index in range(60):
    row=rows[index*3 % len(rows)]
    text=f"{row['description']} at {row['location']} completed, {50 + (index % 2)*50}%."
    if index % 6 == 1: text=text.replace('Erect','Install').replace('spool','segment')
    if index % 6 == 2: text=text.replace(row['activity_code'], row['activity_code'].replace('-',''))
    if index % 6 == 3: text=text.replace(row['location'], row['location'].replace('R03','rack 3'))
    if index % 10 == 0: text=f"Unknown work package ZZ-{index:03d} at offshore platform, 20%."
    reports.append({'text':text,'truth':None if index % 10 == 0 else row['activity_code'],'discipline':row['discipline']})
split=int(len(reports)*.85)
(OUT/'train.jsonl').write_text('\n'.join(json.dumps(item) for item in reports[:split]), encoding='utf-8')
(OUT/'held_out.jsonl').write_text('\n'.join(json.dumps(item) for item in reports[split:]), encoding='utf-8')
print(f'generated {len(rows)} activities, {split} train reports, {len(reports)-split} held-out reports')
