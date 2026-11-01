import asyncio
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    source,target=map(Path,sys.argv[1:3]);target.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel='chrome',headless=True)
        page=await browser.new_page()
        for n in [1,2,4,5,6,9,22,25]:
            svg=next(source.glob(f'{n:02}_*.svg')).read_text(encoding='utf-8-sig')
            w,h=re.search(r'width="(\d+)" height="(\d+)"',svg).groups()
            await page.set_content(f'<style>@page{{size:{w}px {h}px;margin:0}}body{{margin:0}}</style>'+svg)
            await page.pdf(path=str(target/f'fig{n:02}.pdf'),width=f'{w}px',height=f'{h}px',print_background=True,margin={'top':'0','right':'0','bottom':'0','left':'0'})
        await browser.close()
    print('8 vector PDFs exported')

asyncio.run(main())
