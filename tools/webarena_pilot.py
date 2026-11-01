"""One real, read-only WebArena-Verified task; no answer/evaluator data in the planner."""
import asyncio
import json
import time
from pathlib import Path
from unittest.mock import patch
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
from guard.storage import Store, uid
from guard import runner

async def main():
    out=Path('artifacts/runs/webarena-94-hybrid');out.mkdir(parents=True,exist_ok=True)
    state=Path('.data/wa-admin-state.json')
    async with async_playwright() as p:
        b=await p.chromium.launch(channel='chrome',headless=True)
        c=await b.new_context(extra_http_headers={'X-M2-Admin-Auto-Login':'admin:admin1234'})
        page=await c.new_page()
        await page.goto('http://localhost:7780/admin',wait_until='domcontentloaded')
        await page.wait_for_timeout(2000)
        await c.storage_state(path=state)
        await b.close()
    # This file was produced by official agent-input-get, and contains no expected answer.
    source=json.loads(Path('artifacts/wa94-input.json').read_text())[0]
    store=Store();id=uid()
    task=dict(id=id,goal='Start at http://localhost:7780/admin. '+source['intent'],goal_source='benchmark',goal_version=1,
              agent_id='browser-use-local',mode='hybrid',max_steps=16,status='running',created_at=time.time(),result=None,error=None)
    store.put('task',id,task)
    store.event(id,'task_created',{'goal':task['goal'],'mode':'hybrid','benchmark_task_id':94})
    original=runner.Browser
    def browser(**kwargs):
        return original(**kwargs,storage_state=str(state))
    print(json.dumps({'task_id':id,'benchmark_task_id':94}),flush=True)
    with patch.object(runner,'Browser',browser):
        await runner.run_task(store,task)
    task=store.get('task',id)
    artifact={'task':task,'source_task_id':94,'decisions':[d for d in store.all('decision') if d['task_id']==id],
              'events':store.events(id),'source':'webarena-verified==1.2.3','evaluation':'run tools/evaluate_wa94.py in .bench-venv'}
    (out/'run.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':task['status'],'result':task['result'],'error':task['error']},ensure_ascii=True))

asyncio.run(main())
