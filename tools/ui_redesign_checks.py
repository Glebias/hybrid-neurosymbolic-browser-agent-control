"""Read-only live checks + isolated browser fixtures. Never starts an agent or model."""
import asyncio,json,time,copy
from pathlib import Path
from playwright.async_api import async_playwright,expect

BASE='http://127.0.0.1:8765'
async def main():
    checks=[];errors=[];out=Path('artifacts/ui-redesign');out.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel='chrome',headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto(BASE);await page.get_by_role('heading',name='Задачи агента',exact=True).wait_for()
        await page.get_by_text('Локальный сервис доступен',exact=True).wait_for()
        for width in [320,390,760,1440]:
            await page.set_viewport_size({'width':width,'height':900})
            for label in ['Агенты','Подтверждения','Правила защиты','Журнал решений']:
                await page.get_by_role('button',name=label,exact=True).click()
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,label)
            await page.get_by_role('button',name='Агенты',exact=True).click()
            await expect(page.locator('.agent-identity')).to_be_visible()
            if width<=760:
                await page.get_by_role('button',name='История задач').click()
                await expect(page.locator('.task-list button').first).to_be_visible()
                await page.get_by_role('button',name='История задач').click()
            checks.append(f'{width}px: all four views contained; agent and task selection reachable')
        await page.set_viewport_size({'width':1440,'height':1000})
        await page.locator('[data-task-id="507c354bc09d423dbb41361182f0e12f"]').click()
        trigger=page.locator('.timeline-item.block').get_by_role('button',name='Контекст',exact=True)
        await trigger.click();dialog=page.get_by_role('dialog')
        await expect(dialog).to_be_visible()
        assert await dialog.evaluate('(d)=>d.contains(document.activeElement)')
        await dialog.locator('summary').last.focus();await page.keyboard.press('Tab')
        assert await dialog.evaluate('(d)=>d.contains(document.activeElement)||!document.hasFocus()')
        await page.keyboard.press('Escape');await expect(dialog).not_to_be_visible()
        await expect(trigger).to_be_focused()
        checks.append('native modal: focus enters, background inert, Escape closes, focus returns')
        await page.get_by_role('button',name='Новая задача',exact=True).click()
        await page.locator('#goal').focus()
        focus=await page.locator('#goal').evaluate('(e)=>({style:getComputedStyle(e).outlineStyle,width:getComputedStyle(e).outlineWidth})')
        assert focus['style']!='none' and focus['width']!='0px'
        checks.append('task input has a visible keyboard focus indicator')
        await page.get_by_role('button',name='Закрыть новую задачу',exact=True).click()
        await page.get_by_role('button',name='Журнал решений',exact=True).click()
        await page.get_by_label('Фильтр решений',exact=True).select_option('BLOCK')
        rows=page.locator('tbody tr');assert 0<await rows.count()<=20
        for row in await rows.all():await expect(row.locator('.badge')).to_have_text('Заблокировано')
        await page.get_by_label('Поиск в журнале').fill('no-match-canary-2026')
        await expect(page.get_by_role('heading',name='Совпадений нет')).to_be_visible()
        checks.append('journal filters by verdict and search; bounded page size and empty state')
        await page.get_by_role('button',name='Агенты',exact=True).click()
        await page.route('**/api/**',lambda route:route.abort())
        await page.get_by_text('Нет связи с сервисом',exact=True).wait_for()
        await page.get_by_role('button',name='Новая задача',exact=True).click()
        await page.locator('#goal').fill('Do not actually execute this test goal')
        await expect(page.get_by_role('button',name='Запустить задачу')).to_be_disabled()
        checks.append('lost connection is visible and blocks task submission')
        await page.close()

        # Synthetic UI states are fulfilled in this browser only; no backend/model calls.
        now=time.time()
        t={'id':'fixture-task','goal':'Учебная UI-проверка без запуска агента','status':'waiting','mode':'hybrid','created_at':now,'run_kind':'calibration','agent_id':'browser-use-local','result':None}
        def decision(id,verdict,**extra):
            return {'decision_id':id,'task_id':t['id'],'proposal_id':id,'verdict':verdict,'reason':'Учебная причина','rule_ids':['UI_FIXTURE'],
                'approval':None,'expires_at':now+120,'created_at':now,'latency_ms':5,'policy_version':1,'model_skipped':True,'assessment':None,
                'action':{'tool':'click','arguments':{'index':1},'observation':{'url':'http://example.test','target':{'text':'Учебная кнопка'},'page_excerpt':''}},**extra}
        ds=[decision('allowed-no-result','ALLOW'),decision('pending','ASK_USER'),decision('expired','ASK_USER',expires_at=now-1),decision('model-failure','BLOCK',model_skipped=False,rule_ids=['MODEL_UNAVAILABLE'])]
        mutations=[];task_items=[t]
        async def route_api(route):
            path=route.request.url.split('/api',1)[1]
            if route.request.method=='POST':
                mutations.append(path)
                if path=='/tasks':
                    payload=route.request.post_data_json
                    assert payload['request_id'] and payload['mode']=='hybrid'
                    result={'id':'fixture-created','goal':payload['goal'],'status':'queued','mode':payload['mode'],'created_at':time.time(),'agent_id':'browser-use-local'}
                    task_items.insert(0,result)
                else:
                    assert path=='/decisions/pending/approve'
                    ds[1]['approval']=True;t['status']='running'
                    result=ds[1]
            else:result={'/status':{'model':{'configured':True,'calibration':True,'agent_model':'fixture','guard_model':'fixture'},'agents':[{'id':'browser-use-local','name':'Browser Use','status':'idle','verified':True}],'settings':{'strict':False}},'/tasks':task_items,'/decisions':ds,'/events':[],'/rules':[]}[path]
            await route.fulfill(json=result)
        fixture=await browser.new_page(viewport={'width':1100,'height':950})
        fixture.on('pageerror',lambda e:errors.append(str(e)))
        await fixture.route('**/api/**',route_api)
        await fixture.goto(BASE);await fixture.locator('.timeline-item').first.wait_for()
        await expect(fixture.locator('.timeline-item').nth(0)).to_contain_text('Исполнение не подтверждено')
        await expect(fixture.locator('.timeline-item').nth(2)).to_contain_text('Срок ответа истёк')
        await expect(fixture.locator('.inline-approval')).to_have_count(1)
        await fixture.locator('.inline-approval').get_by_role('button',name='Разрешить',exact=True).click()
        await expect(fixture.locator('.inline-approval')).to_have_count(0)
        await expect(fixture.locator('.timeline-item').nth(1)).to_contain_text('Исполнение не подтверждено')
        assert len(mutations)==1
        checks.append('fixture: pending approval submits once; ALLOW/approved are not shown as executed; expired request is closed')
        await fixture.locator('.timeline-item.block').get_by_role('button',name='Контекст',exact=True).click()
        await expect(fixture.get_by_role('dialog')).to_contain_text('Оценку модели получить не удалось')
        checks.append('fixture: model failure is distinguished from a skipped model call')
        await fixture.keyboard.press('Escape')
        await fixture.get_by_role('button',name='Новая задача',exact=True).click()
        await fixture.locator('#goal').fill('Изолированная проверка постановки задачи')
        await fixture.get_by_role('button',name='Запустить задачу',exact=True).click()
        await expect(fixture.locator('.task-goal>p')).to_have_text('Изолированная проверка постановки задачи')
        await expect(fixture.locator('.run-heading .badge')).to_have_text('В очереди')
        assert mutations.count('/tasks')==1
        checks.append('fixture: new-task composer sends one idempotent request, selects queued task, and closes')
        await browser.close()
    assert not errors,errors
    report={'status':'passed','checks':checks,'page_errors':errors,'agent_tasks_started':0,'model_api_calls':0,
        'scope':'Live read-only history plus isolated UI request fixtures; not an autonomous-agent run'}
    (out/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(checks),'page_errors':errors,'agent_tasks_started':0}))

asyncio.run(main())
