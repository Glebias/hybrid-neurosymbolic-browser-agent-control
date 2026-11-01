import json
from pathlib import Path
import httpx
import pytest
from guard import free_api, policy
from guard.app import create_app
from guard.codex_backend import command, SAFE_ENV
from guard.models import Action,Observation,Assessment

def test_unknown_conditions_do_not_become_permission():
    c={'all':[{'field':'known','op':'eq','value':True},{'field':'missing','op':'eq','value':False}]}
    assert policy.evaluate(c,{'known':True}) is None
    assert policy.evaluate(c,{'known':False}) is False
    assert policy.evaluate({'any':c['all']},{'known':True}) is True

def test_base_rules_update_without_code(tmp_path,monkeypatch):
    data=policy.catalog()
    data['rules'].insert(0,{'id':'NEW_BASE_RULE','stage':'pre','priority':0,'when':{'field':'tool','op':'eq','value':'input'},'verdict':'BLOCK','reason':'New base rule'})
    file=tmp_path/'base.json';file.write_text(json.dumps(data),encoding='utf-8')
    monkeypatch.setattr(policy,'CATALOG',file)
    a=Action(proposal_id='p',task_id='t',tool='input',observation=Observation(fingerprint='context'))
    assert policy.initial(a,[])[2][0]=='NEW_BASE_RULE'

def test_explicit_authorization_reduces_confirmation():
    a=Action(proposal_id='p',task_id='t',tool='click',observation=Observation(fingerprint='context'))
    explicit=Assessment(effect='send',alignment='aligned',authorization='explicit',authorization_evidence='отправь заявку',explanation='Явное поручение')
    assert policy.resolve(a,explicit,[])[0]=='ALLOW'
    ambiguous=explicit.model_copy(update={'authorization':'unclear'})
    assert policy.resolve(a,ambiguous,[])[0]=='ASK_USER'
    assert policy.resolve(a,explicit.model_copy(update={'alignment':'conflicts'}),[])[0]=='BLOCK'
    assert policy.resolve(a,explicit.model_copy(update={'uncertain':True}),[])[0]=='BLOCK'

def test_no_paid_provider_or_model(monkeypatch):
    for provider,model in [('groq','paid-model'),('zai','glm-4.7'),('google','gemini-2.5-pro'),('openrouter','nvidia/nemotron-3.5-super-vl')]:
        with pytest.raises(ValueError):free_api.credentials(provider,model)
    monkeypatch.setenv('GROQ_API_KEY','test-only')
    monkeypatch.setenv('GROQ_FREE_PLAN_CONFIRMED','false')
    with pytest.raises(ValueError):free_api.credentials('groq','openai/gpt-oss-120b')
    monkeypatch.setenv('GOOGLE_API_KEY','test-only')
    monkeypatch.setenv('GOOGLE_FREE_PLAN_CONFIRMED','false')
    with pytest.raises(ValueError):free_api.credentials('google','gemini-2.5-flash')

def test_codex_call_permissions_and_secret_environment(monkeypatch,tmp_path):
    monkeypatch.setattr('guard.codex_backend.executable',lambda:'codex.exe')
    cmd=command(tmp_path,tmp_path/'schema.json',tmp_path/'response.json',[])
    assert cmd[cmd.index('--sandbox')+1]=='read-only'
    assert '--ignore-user-config' in cmd and '--ephemeral' in cmd
    assert 'forced_login_method="chatgpt"' in cmd and 'web_search="disabled"' in cmd
    assert 'shell_tool' in cmd and 'apps' in cmd and 'browser_use' in cmd
    assert not any('API_KEY' in x or 'TOKEN' in x for x in SAFE_ENV)

async def test_general_runtime_never_sends_arbitrary_data_to_nvidia():
    from guard.model_runtime import infer
    with pytest.raises(ValueError,match='synthetic'):
        await infer('openrouter','nvidia/nemotron-3.5-super-vl:free',[],{})

async def test_free_limit_retries_same_endpoint_and_stops_on_daily_quota(monkeypatch):
    calls=[];waits=[]
    async def sleep(seconds):waits.append(seconds)
    monkeypatch.setattr('guard.free_api.asyncio.sleep',sleep)
    def handler(request):
        calls.append(str(request.url))
        if len(calls)==1:return httpx.Response(429,headers={'Retry-After':'1'},json={'error':{}})
        return httpx.Response(200,json={'ok':True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await free_api.post_with_limits(client,'https://api.example.test/free',json={})
    assert result.json()['ok'] and len(calls)==2 and len(set(calls))==1 and waits==[1.25]
    def exhausted(request):
        return httpx.Response(429,json={'error':{'details':[{'violations':[{'quotaId':'FreeRequestsPerDay'}]}]}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(exhausted)) as client:
        with pytest.raises(free_api.FreeQuotaExceeded):
            await free_api.post_with_limits(client,'https://api.example.test/free',json={})
    assert waits==[1.25]

async def test_task_request_replay_and_cancel(tmp_path,monkeypatch):
    app=create_app(tmp_path/'api.db',start_worker=False)
    app.state.store.put('agent','browser-use-local',{'id':'browser-use-local'})
    monkeypatch.setattr('guard.analysis.configured',lambda:True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        payload={'goal':'Найти ноутбук без покупки','request_id':'request-1'}
        a=(await c.post('/api/tasks',json=payload)).json()
        b=(await c.post('/api/tasks',json=payload)).json()
        assert a['id']==b['id']
        assert len((await c.get('/api/tasks')).json())==1
        assert (await c.post('/api/tasks',json={**payload,'goal':'Другое поручение'})).status_code==409
        assert (await c.post('/api/tasks/'+a['id']+'/cancel')).json()['status']=='cancelled'
        assert (await c.post('/api/tasks/'+a['id']+'/cancel')).status_code==409
