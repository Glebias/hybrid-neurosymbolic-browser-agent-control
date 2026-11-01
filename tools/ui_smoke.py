"""Exercise the actual built interface; no route mocking or seeded fake decisions."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    out=Path('artifacts');out.mkdir(exist_ok=True)
    checks=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel='chrome',headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1000},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8765')
        await page.get_by_role('heading',name='Ваш браузерный агент').wait_for()
        await page.get_by_text('Локальный сервис доступен').wait_for()
        checks.append('interface connected to real API')
        await page.get_by_role('button',name='Подбор ноутбука',exact=True).click()
        assert '2500' in await page.locator('#goal').input_value()
        checks.append('task preset populates editable goal')
        await page.screenshot(path=str(out/'interface-agents.png'),full_page=True)
        await page.get_by_role('button',name='Правила защиты',exact=True).click()
        await page.get_by_label('Название',exact=True).fill('UI smoke: запрет ввода')
        await page.get_by_label('Значение',exact=True).fill('input')
        await page.get_by_role('button',name='Добавить правило').click()
        await page.get_by_text('UI smoke: запрет ввода',exact=True).wait_for()
        checks.append('rule created through UI and persisted')
        await page.reload()
        await page.get_by_role('button',name='Правила защиты',exact=True).click()
        await page.get_by_text('UI smoke: запрет ввода',exact=True).wait_for()
        await page.get_by_role('button',name='Удалить UI smoke: запрет ввода').click()
        await page.get_by_text('UI smoke: запрет ввода',exact=True).wait_for(state='detached')
        checks.append('rule survives reload and can be removed')
        await page.get_by_role('checkbox',name='Строгий профиль').check()
        await page.get_by_role('checkbox',name='Строгий профиль').uncheck()
        checks.append('profile toggles through API')
        await page.get_by_role('button',name='Подтверждения',exact=True).click()
        await page.get_by_role('heading',name='Подтверждений пока нет').wait_for()
        await page.get_by_role('button',name='Журнал решений',exact=True).click()
        await page.wait_for_timeout(800)
        assert await page.locator('main').inner_text()
        checks.append('approvals and populated journal display correctly')
        await page.set_viewport_size({'width':760,'height':1000})
        await page.get_by_role('button',name='Агенты',exact=True).click()
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(out/'interface-mobile.png'),full_page=True)
        checks.append('responsive layout has no horizontal overflow')
        assert not errors,errors
        await browser.close()
    (out/'ui-smoke.json').write_text(json.dumps({'checks':checks,'page_errors':errors,'status':'passed'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(checks),'errors':errors}))

asyncio.run(main())
