#!/usr/bin/env python3
"""快速爬取当天新闻联播列表 - 绕过日历交互"""
import asyncio
import json
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright

async def quick_crawl():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        print("访问新闻联播页面...")
        await page.goto("https://tv.cctv.com/lm/xwlb/", wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(5000)
        
        # 滚动加载更多
        print("滚动加载...")
        for i in range(5):
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(1000)
        await page.wait_for_timeout(5000)
        
        # 获取所有VIDE链接
        links = await page.evaluate("""() => {
            const allLinks = document.querySelectorAll('a[href*=\"/VIDE\"]');
            const results = [];
            const seen = new Set();
            allLinks.forEach(link => {
                const href = link.href;
                const text = link.textContent.trim();
                const urlKey = href.split('?')[0];
                if (seen.has(urlKey) || !text || text.length < 5) return;
                seen.add(urlKey);
                results.push({ title: text, url: href });
            });
            return results;
        }""")
        
        print(f"\n找到 {len(links)} 条链接")
        for l in links:
            print(f"  [{l['title'][:60]}]")
            print(f"    {l['url']}")
        
        # 提取日期
        today = datetime.now().strftime("%Y%m%d")
        filtered = []
        for l in links:
            m = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', l["url"])
            if m:
                date_str = m.group(1)+m.group(2)+m.group(3)
            else:
                date_str = today
            
            # 跳过"完整版 新闻联播"这种
            if "新闻联播" in l["title"] and "完整版" in l["title"]:
                print(f"  跳过完整版: {l['title'][:40]}")
                continue
                
            filtered.append({
                "title": l["title"],
                "url": l["url"],
                "date": date_str
            })
        
        print(f"\n过滤后: {len(filtered)} 条")
        for f in filtered:
            print(f"  [{f['date']}] {f['title'][:60]}")
        
        await browser.close()
        return filtered

result = asyncio.run(quick_crawl())
print(f"\n最终结果: {len(result)} 条")

# 保存
today_str = datetime.now().strftime("%Y%m%d")
out = {}
for i, item in enumerate(result, 1):
    out[str(i)] = {
        "title": item["title"],
        "detail_url": item["url"],
        "date": item["date"],
        "content": "",
        "video_url": "",
        "video_path": "",
        "video_downloaded": False,
        "crawl_time": datetime.now().isoformat()
    }

path = os.path.join(os.path.dirname(__file__), "dic_all_video.json")
if os.path.exists(path):
    # 合并
    with open(path, "r", encoding="utf-8") as f:
        existing = json.load(f)
    # 替换或追加
    for k, v in out.items():
        existing[k] = v
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f"合并到 dic_all_video.json，共 {len(existing)} 条")
else:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"保存 dic_all_video.json，{len(out)} 条")
