"""Retain successful and unsuccessful pilot outcomes without merging calibration and API runs."""
import json
from pathlib import Path
from collections import Counter

rows=[]
for p in sorted(Path('artifacts/runs').glob('*/run.json')):
    r=json.loads(p.read_text(encoding='utf-8'));t=r['task'];decisions=r.get('decisions',[])
    timing=[e['data'] for e in r.get('events',[]) if e['kind']=='guard_timing']
    rows.append({'run':p.parent.name,'task_id':t['id'],'status':t['status'],'models':t.get('model_config'),
        'kind':t.get('run_kind'),'elapsed_s':r.get('elapsed_s',round(t.get('finished_at',0)-t.get('started_at',0),2)),
        'verdicts':dict(Counter(d['verdict'] for d in decisions)),
        'service_latency_ms':[d['latency_ms'] for d in decisions],
        'guard_overhead_ms':[e['guard_overhead_ms'] for e in timing],
        'human_wait_ms':sum(e['human_wait_ms'] for e in timing),
        'synthetic_leaks':r.get('synthetic_leaks'),'attacker_visits':r.get('attacker_visits'),
        'approvals':r.get('approvals_via_ui'),'acceptance':r.get('acceptance'),
        'errors':t.get('errors'),'error':t.get('error'),'source':str(p)})
Path('artifacts/pilot-summary.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
out=Path('artifacts/evidence');out.mkdir(exist_ok=True)
for tag in ['api-control-demo-v3','hidden-codex-off-01','hidden-codex-hybrid-01','hidden-api-off-01','hidden-api-hybrid-01',
            'doom-codex-off-01','doom-codex-hybrid-01','benign-codex-hybrid-03','webarena-94-hybrid']:
    src=Path('artifacts/runs')/tag/'run.json'
    if src.exists():(out/(tag+'.json')).write_bytes(src.read_bytes())
evaluation=Path('artifacts/runs/webarena-94-hybrid/official-evaluation.json')
if evaluation.exists():(out/'webarena-94-evaluation.json').write_bytes(evaluation.read_bytes())
print(f'{len(rows)} recorded pilot outcomes; selected evidence retained')
