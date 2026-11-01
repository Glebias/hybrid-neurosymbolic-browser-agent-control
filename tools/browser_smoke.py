"""Real Chrome + Browser Use executor smoke; assessment stub is explicitly test-only.
This is not evidence of a real model-planned agent run.
"""
import asyncio
import json
from pathlib import Path
import httpx
from browser_use import Browser
from guard.app import create_app
from guard.integration import GuardedTools
from guard.models import Assessment
from guard.storage import uid

async def main():
    async def test_assessor(goal,action):
        return Assessment(effect='navigate' if action.tool=='navigate' else 'input',alignment='aligned',explanation='Тестовый ответ для проверки реального исполнителя')
    app=create_app(Path('.data/browser-smokes')/(uid()+'.db'),assessor=test_assessor,start_worker=False)
    store=app.state.store
    store.put('task','smoke',dict(id='smoke',goal='Проверить учебную страницу',status='running',mode='hybrid'))
    store.put('settings','main',dict(version=1,strict=False))
    tools=GuardedTools('smoke',transport=httpx.ASGITransport(app=app))
    browser=Browser(headless=True,executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',enable_default_extensions=False)
    results={}
    try:
        await browser.start()
        model=tools.registry.create_action_model()
        r=await tools.act(model(navigate={'url':'http://127.0.0.1:8765/lab','new_tab':False}),browser)
        results['navigate']={'error':r.error,'result':r.extracted_content}
        assert not r.error,r.error
        for _ in range(15):
            state=await browser.get_browser_state_summary()
            if 'Ноутбуки для учёбы' in state.dom_state.llm_representation():
                break
            await asyncio.sleep(.3)
        assert 'Ноутбуки для учёбы' in state.dom_state.llm_representation()
        nodes=state.dom_state.selector_map
        input_index=next(i for i,n in nodes.items() if n.attributes.get('name')=='name')
        r=await tools.act(model(input={'index':input_index,'text':'Smoke user','clear':True}),browser)
        results['input']={'error':r.error,'result':r.extracted_content}
        assert not r.error,r.error
        store.put('rule','block-input',dict(id='block-input',field='tool',value='input',verdict='BLOCK',enabled=True))
        state=await browser.get_browser_state_summary()
        input_index=next(i for i,n in state.dom_state.selector_map.items() if n.attributes.get('name')=='name')
        r=await tools.act(model(input={'index':input_index,'text':'MUST NOT APPEAR','clear':True}),browser)
        assert 'GUARD BLOCK' in r.error
        state=await browser.get_browser_state_summary()
        node=next(n for n in state.dom_state.selector_map.values() if n.attributes.get('name')=='name')
        session=await browser.get_or_create_cdp_session()
        current=await session.cdp_client.send.Runtime.evaluate(params={'expression':"document.querySelector('input[name=name]').value",'returnByValue':True},session_id=session.session_id)
        assert current['result']['value']=='Smoke user',current
        # Browser Use's observed field state should retain the previous input.
        results['blocked_input']={'error':r.error,'field_attributes':node.attributes}
        results['decisions']=[{'verdict':d['verdict'],'tool':d['action']['tool']} for d in store.all('decision')]
        results['status']='passed'
    finally:
        await tools.close_client()
        await browser.kill()
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/browser-smoke.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':results['status'],'decisions':results['decisions']}))

if __name__=='__main__':asyncio.run(main())
