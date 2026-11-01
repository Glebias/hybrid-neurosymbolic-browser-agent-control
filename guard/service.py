import asyncio
import base64
import hashlib
import json
import os
import time
from . import analysis, policy
from .models import Action, Decision
from .storage import Store, uid

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def action_digest(action):
    d = action.model_dump()
    # Timing and recent-history growth do not change the proposed browser effect.
    d.pop('recent_actions',None)
    d['observation'].pop('captured_at',None)
    d['observation'].pop('screenshot',None)
    return digest(d)

def visible_action(action):
    d = action.model_dump()
    if action.payload_class == 'secret':
        d['arguments'] = {'redacted':'секретное содержимое скрыто'}
    # Screenshots are local evidence, not repeated in each event.
    d['observation'].pop('screenshot',None)
    return d

class GuardService:
    def __init__(self, store: Store, assessor=analysis.assess):
        self.store, self.assessor = store, assessor
        self.lock = asyncio.Lock()

    async def decide(self, action: Action):
        # Serializes same-proposal replays and avoids duplicate model charges.
        async with self.lock:
            task = self.store.get('task',action.task_id)
            if not task or task['status'] not in {'running','waiting'}:
                raise ValueError('Задача не активна')
            old = self.store.get('proposal',action.proposal_id)
            fingerprint = action_digest(action)
            if old:
                if old['hash'] != fingerprint or old['task_id'] != action.task_id:
                    raise ValueError('proposal_id повторён с другим действием')
                return self.store.get('decision',old['decision_id'])
            start = time.perf_counter()
            settings = self.store.get('settings','main') or {'version':1,'strict':False}
            rules = self.store.all('rule')
            mode = task.get('mode','hybrid')
            facts, skipped = None, True
            pre = policy.initial(action,rules)
            if mode == 'off':
                answer = ('ALLOW','Контроль отключён для сравнительного эксперимента.', ['EXPERIMENT_OFF'])
            elif pre and (mode != 'neural' or pre[0] == 'BLOCK'):
                answer = pre
            else:
                if mode != 'symbolic':
                    try:
                        facts = await self.assessor(task['goal'],action)
                        skipped = False
                    except Exception as exc:
                        answer = ('BLOCK','Смысловой анализ недоступен или вернул некорректные данные.', ['MODEL_UNAVAILABLE'])
                        self.store.event(action.task_id,'analysis_error',{'type':type(exc).__name__})
                        facts = None
                        skipped = False
                        # Explicit failure does not fall back to permissive rules.
                        return self._save(action,task,fingerprint,answer,None,skipped,start,settings)
                if mode == 'neural' and facts:
                    if facts.alignment in {'conflicts','unrelated'} or facts.injection_suspected:
                        answer = ('BLOCK',facts.explanation,['NEURAL'])
                    elif facts.uncertain or facts.effect in {'purchase','delete','send','auth','unknown'}:
                        answer = ('ASK_USER',facts.explanation,['NEURAL'])
                    else:
                        answer = ('ALLOW',facts.explanation,['NEURAL'])
                else:
                    answer = policy.resolve(action,facts,rules,settings.get('strict',False))
            return self._save(action,task,fingerprint,answer,facts,skipped,start,settings)

    def _save(self,action,task,fingerprint,answer,facts,skipped,start,settings):
        verdict, reason, rule_ids = answer
        d = Decision(decision_id=uid(),proposal_id=action.proposal_id,verdict=verdict,reason=reason,rule_ids=rule_ids,
                     assessment=facts,model_skipped=skipped,latency_ms=round((time.perf_counter()-start)*1000,2),
                     policy_version=settings.get('version',1),expires_at=time.time()+int(os.getenv('CONFIRMATION_TIMEOUT','120')) if verdict=='ASK_USER' else None).model_dump()
        d.update(task_id=action.task_id,action=visible_action(action),action_hash=fingerprint,created_at=time.time(),approval=None)
        d['has_screenshot']=False
        if action.observation.screenshot and action.payload_class != 'secret':
            try:
                raw=base64.b64decode(action.observation.screenshot,validate=True)
                if raw.startswith(b'\x89PNG') and len(raw)<8_000_000:
                    folder=self.store.path.parent/'screenshots'
                    folder.mkdir(exist_ok=True)
                    (folder/(d['decision_id']+'.png')).write_bytes(raw)
                    d['has_screenshot']=True
            except ValueError:
                pass
        self.store.put('decision',d['decision_id'],d)
        self.store.put('proposal',action.proposal_id,{'decision_id':d['decision_id'],'hash':fingerprint,'task_id':action.task_id})
        self.store.event(action.task_id,'decision',d)
        if verdict == 'ASK_USER':
            task.update(status='waiting')
            self.store.put('task',task['id'],task)
        return d

    def approval(self,id,allow):
        d = self.store.get('decision',id)
        if not d or d['verdict'] != 'ASK_USER' or d['approval'] is not None:
            raise ValueError('Запрос подтверждения отсутствует или уже обработан')
        task = self.store.get('task',d['task_id'])
        if time.time() > d['expires_at'] or task['status'] not in {'running','waiting'}:
            raise ValueError('Запрос истёк или задача завершена')
        d['approval'] = bool(allow)
        d['answered_at'] = time.time()
        self.store.put('decision',id,d)
        task['status'] = 'running'
        self.store.put('task',task['id'],task)
        self.store.event(task['id'],'approval',{'decision_id':id,'allowed':bool(allow)})
        return d
