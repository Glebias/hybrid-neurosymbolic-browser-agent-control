"""Browser Use 0.13.14 integration: a mandatory gate in Tools.act.

No second CDP observer: observations come from the agent's own BrowserSession.
The original executor is invoked only by this class after an explicit decision.
"""
import asyncio
import json
import os
import time
import re
from urllib.parse import urljoin, urlparse
from uuid import uuid4
import httpx
from browser_use import Tools, ActionResult
from .models import Action, Observation
from .service import digest

EXCLUDED = ['evaluate','upload_file','save_as_pdf','write_file','replace_file','read_file']

class GuardedTools(Tools):
    def __init__(self, task_id, base_url=None, transport=None):
        super().__init__(exclude_actions=EXCLUDED)
        self.task_id = task_id
        self.client = httpx.AsyncClient(base_url=base_url or os.getenv('GUARD_URL','http://127.0.0.1:8765'),timeout=200,transport=transport,trust_env=False)
        self.recent = []

    async def close_client(self):
        await self.client.aclose()

    async def observe(self, browser, params, fresh=False):
        try:
            state = await browser.get_browser_state_summary(include_screenshot=True,cached=not fresh)
            target = {}
            index = params.get('index')
            if index is not None:
                node = state.dom_state.selector_map.get(index)
                if node:
                    target = dict(backend_node_id=node.backend_node_id,tag=node.node_name,
                                  attributes={k:v for k,v in node.attributes.items() if k in {'type','role','href','name','id','action','formaction','placeholder','value'}},
                                  text=node.get_all_children_text(max_depth=3)[:1500])
                    p = node.parent_node
                    for _ in range(5):
                        if p is None:
                            break
                        if p.node_name.lower() == 'form':
                            target['form']={'attributes':p.attributes,'text':p.get_all_children_text(max_depth=5)[:2500]}
                            # A submit button can override its parent form's destination.
                            destination=urljoin(state.url,node.attributes.get('formaction') or p.attributes.get('action','') or state.url)
                            fields=[]
                            def visit(n,depth=0):
                                if depth>8:return
                                attrs=getattr(n,'attributes',{})
                                if getattr(n,'node_name','').lower() in {'input','textarea','select'}:
                                    name=attrs.get('name','')
                                    sensitive=bool(re.search(r'(token|secret|password|api.?key|cookie)',name,re.I))
                                    field={'name':name,'type':attrs.get('type','text'),'sensitive':sensitive}
                                    value=attrs.get('value','')
                                    # Small primitive query parameters help distinguish a filter from an unexplained transfer.
                                    # Never copy secret, free-text or high-entropy hidden values into the model context.
                                    if not sensitive and (re.fullmatch(r'-?\d{1,7}(?:\.\d{1,6})?',value) or value.lower() in {'true','false'}):
                                        field['value']=value
                                    fields.append(field)
                                for child in getattr(n,'children_nodes',None) or []:visit(child,depth+1)
                            visit(p)
                            target['form'].update(destination=destination,fields=fields)
                            source_url,dest_url=urlparse(state.url),urlparse(destination)
                            foreign=(source_url.scheme,source_url.netloc)!=(dest_url.scheme,dest_url.netloc)
                            target['cross_origin_secret_form']=foreign and any(f['sensitive'] for f in fields)
                            break
                        p = p.parent_node
                else:
                    target={'missing_index':index}
            excerpt = state.dom_state.llm_representation()[:12000]
            fp = digest({'url':state.url,'target':target})
            return Observation(url=state.url,title=state.title,target=target,page_excerpt=excerpt,
                               screenshot=state.screenshot,captured_at=time.time(),fingerprint=fp)
        except Exception as exc:
            return Observation(page_excerpt='Context unavailable: '+type(exc).__name__,captured_at=time.time())

    async def record(self, kind, data):
        r = await self.client.post(f'/api/tasks/{self.task_id}/events',json={'kind':kind,'data':data})
        r.raise_for_status()

    async def act(self, action, browser_session, **kwargs):
        started=time.perf_counter();timing={'human_wait_ms':0,'execution_ms':0}
        try:
            return await self._guarded_act(action,browser_session,timing,**kwargs)
        finally:
            if timing.get('wait_started'):
                timing['human_wait_ms']+=(time.perf_counter()-timing.pop('wait_started'))*1000
            timing['guard_overhead_ms']=round((time.perf_counter()-started)*1000-timing['human_wait_ms']-timing['execution_ms'],2)
            timing['human_wait_ms']=round(timing['human_wait_ms'],2)
            timing['execution_ms']=round(timing['execution_ms'],2)
            try:
                await self.record('guard_timing',timing)
            except Exception:
                pass

    async def _guarded_act(self, action, browser_session, timing, **kwargs):
        entries = [(k,v) for k,v in action.model_dump(exclude_unset=True).items() if v is not None]
        if len(entries) != 1:
            return ActionResult(error='GUARD BLOCK P0: expected one atomic tool call')
        tool, params = entries[0]
        params = params or {}
        observation = await self.observe(browser_session,params)
        description = getattr(self.registry.registry.actions.get(tool),'description','')
        secret = observation.target.get('attributes',{}).get('type') == 'password' or observation.target.get('cross_origin_secret_form',False)
        proposal = Action(proposal_id=uuid4().hex,task_id=self.task_id,tool=tool,arguments=params,description=description,
                          observation=observation,recent_actions=self.recent[-5:],payload_class='secret' if secret else 'ordinary')
        try:
            r = await self.client.post('/api/decide',json=proposal.model_dump())
            r.raise_for_status()
            decision = r.json()
            timing['decision_id']=decision['decision_id']
            if decision['verdict'] == 'ASK_USER':
                timing['wait_started']=time.perf_counter()
                while True:
                    if time.time() >= decision['expires_at']:
                        await self.record('confirmation_expired',{'decision_id':decision['decision_id']})
                        await self.client.post(f'/api/tasks/{self.task_id}/proposals/{proposal.proposal_id}/cancel')
                        return ActionResult(error='GUARD BLOCK: confirmation expired. Tool was NOT executed.')
                    await asyncio.sleep(.5)
                    r = await self.client.get('/api/decisions/'+decision['decision_id'])
                    r.raise_for_status()
                    current = r.json()
                    if current['approval'] is not None:
                        if not current['approval']:
                            return ActionResult(error='GUARD BLOCK: user rejected this action. Tool was NOT executed.')
                        break
                timing['human_wait_ms']=(time.perf_counter()-timing.pop('wait_started'))*1000
            elif decision['verdict'] != 'ALLOW':
                self.recent.append({'tool':tool,'status':'blocked','reason':decision['reason']})
                return ActionResult(error='GUARD BLOCK: '+decision['reason']+' Tool was NOT executed. Replan within the user goal.')
            # Task cancellation, policy changes and target replacement invalidate old permission.
            task_r = await self.client.get('/api/tasks/'+self.task_id)
            task_r.raise_for_status()
            if task_r.json()['status'] not in {'running','waiting'}:
                return ActionResult(error='GUARD BLOCK: task cancelled or ended')
            status_r = await self.client.get('/api/status')
            status_r.raise_for_status()
            if status_r.json()['settings']['version'] != decision['policy_version']:
                return ActionResult(error='GUARD BLOCK: policy changed. Propose the action again.')
            if status_r.json().get('base_policy_hash') != decision.get('base_policy_hash'):
                return ActionResult(error='GUARD BLOCK: base policy changed. Propose again.')
            if tool not in {'done','wait'}:
                fresh = await self.observe(browser_session,params,fresh=True)
                if not observation.fingerprint or fresh.fingerprint != observation.fingerprint:
                    await self.record('stale_context',{'decision_id':decision['decision_id']})
                    return ActionResult(error='GUARD BLOCK: page or target changed during review. Observe and propose again.')
        except asyncio.CancelledError:
            try:
                await asyncio.wait_for(asyncio.shield(self.client.post(f'/api/tasks/{self.task_id}/proposals/{proposal.proposal_id}/cancel')),timeout=3)
            except Exception:
                pass
            raise
        except (httpx.HTTPError,KeyError,ValueError):
            return ActionResult(error='GUARD_UNAVAILABLE: safety service failed. Tool was NOT executed.')
        # Waiting for a human happens outside the original per-tool timeout.
        # The Agent step timeout is separately configured above confirmation + model budget.
        execution_start=time.perf_counter()
        try:
            result = await super().act(action,browser_session,**kwargs)
        finally:
            timing['execution_ms']=(time.perf_counter()-execution_start)*1000
        self.recent.append({'tool':tool,'status':'error' if result.error else 'executed','summary':(result.error or result.extracted_content or '')[:1000]})
        try:
            await self.record('execution_result',{'decision_id':decision['decision_id'],'tool':tool,'success':not bool(result.error),
                                                'summary':(result.error or result.extracted_content or '')[:3000]})
        except httpx.HTTPError:
            # Never repeat a browser effect because its audit delivery failed.
            return ActionResult(error='GUARD_RESULT_UNKNOWN: tool was invoked but result could not be recorded. Do not repeat irreversible effects.')
        return result
