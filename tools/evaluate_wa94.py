"""Official deterministic evaluation; no LLM judge, no guessed answer."""
import json
from pathlib import Path
from webarena_verified.api import WebArenaVerified
from webarena_verified.types.config import WebArenaVerifiedConfig
from webarena_verified.types.tracing import NetworkTrace

out=Path('artifacts/runs/webarena-94-hybrid')
run=json.loads((out/'run.json').read_text(encoding='utf-8'))
text=(run['task'].get('result') or '').strip()
try:
    number=float(text)
    response={'task_type':'RETRIEVE','status':'SUCCESS','retrieved_data':[number],'error_details':None}
except ValueError:
    response={'task_type':'RETRIEVE','status':'UNKNOWN_ERROR','retrieved_data':None,'error_details':text}
wa=WebArenaVerified(config=WebArenaVerifiedConfig(environments={'__SHOPPING_ADMIN__':{'urls':['http://localhost:7780/admin']}}))
# Task 94 uses only the agent-response evaluator; empty trace is explicit, not a fabricated HAR.
result=wa.evaluate_task(task_id=94,agent_response=response,
                        network_trace=NetworkTrace(is_playwright=False,src_file=out/'no-network-trace',events=()))
(out/'official-evaluation.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
print(result.model_dump_json(indent=2))
