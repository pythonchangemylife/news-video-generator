#!/usr/bin/env python3
"""
CCTV 新闻联播爬虫 - Playwright 版本
支持选择指定日期爬取新闻
"""

import asyncio
import re
import json
import time
import os
from pathlib import Path
from datetime import datetime

# ==================== 配置 ====================

class Config:
    """配置类"""
    BASE_URL = "https://tv.cctv.com"
    NEWS_LIST_URL = "https://tv.cctv.com/lm/xwlb/"
    
    # 输出目录
    OUTPUT_DIR = Path("output")
    VIDEOS_RAW = Path("videos_raw")  # 原始视频目录
    TEXT_DIR = OUTPUT_DIR / "text"
    ALL_VIDEO_JSON = Path("dic_all_video.json")  # JSON 文件保存到项目根目录
    
    # 最大爬取数量
    MAX_NEWS = 20
    
    @classmethod
    def setup(cls):
        """创建必要的目录"""
        cls.OUTPUT_DIR.mkdir(exist_ok=True)
        cls.VIDEOS_RAW.mkdir(exist_ok=True)
        cls.TEXT_DIR.mkdir(exist_ok=True)


# ==================== 工具函数 ====================

def load_json(file_path):
    """加载 JSON 文件"""
    if not file_path.exists():
        return {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_json(file_path, data):
    """保存 JSON 文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ==================== 视频爬虫类 ====================

class XWLBCrawler:
    """新闻联播爬虫（Playwright 版本）"""
    
    def __init__(self):
        Config.setup()
        self.dic_all_video = load_json(Config.ALL_VIDEO_JSON)
    
    def select_date(self, target_date=None):
        """选择日期。如果传入了 target_date 直接使用，否则返回 None（爬取最新）。"""
        # 如果提供了目标日期，统一转换为 YYYYMMDD 格式
        if target_date:
            print(f"📅 指定日期：{target_date}")
            date_str = target_date.replace('-', '').replace('/', '')
            if len(date_str) == 8 and date_str.isdigit():
                return date_str
            else:
                print(f"⚠️ 日期格式错误，将爬取最新新闻")
                return None
        
        # 非交互模式：默认爬取最新新闻
        return None
    
    async def crawl_with_playwright(self, target_date):
        """使用 Playwright 爬取指定日期的新闻"""
        from playwright.async_api import async_playwright
        
        target_day = int(target_date[6:8]) if target_date else None
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # 1. 访问主页
            print("📺 访问 CCTV 新闻联播页面...")
            await page.goto(Config.NEWS_LIST_URL, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(8000)  # 等待额外 8s 让动态内容加载
            
            # 2. 点击日历（如果指定了日期）
            if target_day:
                print("📅 打开日历面板...")
                calendar_clicked = False
                try:
                    elements = await page.query_selector_all('div, a, span, button')
                    for elem in elements:
                        text = await elem.text_content()
                        if text and ('日历' in text or 'date' in text.lower()):
                            try:
                                await elem.click(timeout=5000)
                                await page.wait_for_timeout(3000)
                                print("✓ 日历已打开（通过文本）")
                                calendar_clicked = True
                                break
                            except:
                                continue
                    
                    if not calendar_clicked:
                        calendar_selectors = [
                            '.calendar-icon',
                            '.date-picker',
                            '[class*="calendar"]',
                            '[class*="date"]',
                            '.el-date-editor',
                            '.ant-calendar-picker'
                        ]
                        for selector in calendar_selectors:
                            try:
                                elem = await page.query_selector(selector)
                                if elem:
                                    await elem.click(timeout=5000)
                                    await page.wait_for_timeout(3000)
                                    print(f"✓ 日历已打开（通过选择器 {selector}）")
                                    calendar_clicked = True
                                    break
                            except:
                                continue
                    
                    if not calendar_clicked:
                        print("⚠️ 无法打开日历，尝试直接滚动页面获取内容...")
                
                except Exception as e:
                    print(f"⚠️ 打开日历出错：{e}，尝试直接滚动页面...")
                
                # 3. 选择日期
                if calendar_clicked:
                    print(f"📅 选择日期 {target_day}...")
                    try:
                        await page.wait_for_timeout(2000)
                        
                        day_selectors = [
                            f'td:has-text("{target_day}")',
                            f'div:has-text("{target_day}")',
                            f'span:has-text("{target_day}")',
                            f'.day-{target_day}',
                            f'[data-day="{target_day}"]'
                        ]
                        
                        for selector in day_selectors:
                            try:
                                day_elem = await page.query_selector(selector)
                                if day_elem:
                                    is_visible = await day_elem.is_visible()
                                    if is_visible:
                                        await day_elem.click(timeout=5000)
                                        print(f"✓ 已点击日期 {target_day}（通过选择器 {selector}）")
                                        break
                            except:
                                continue
                        else:
                            day_cells = await page.query_selector_all('td, div[class*="day"], span[class*="day"]')
                            for cell in day_cells:
                                text = await cell.text_content()
                                if text and text.strip() == str(target_day):
                                    try:
                                        is_visible = await cell.is_visible()
                                        if is_visible:
                                            await cell.click(timeout=5000)
                                            print(f"✓ 已点击日期 {target_day}（通过通用方法）")
                                            break
                                    except:
                                        continue
                    except Exception as e:
                        print(f"⚠️ 选择日期出错：{e}")
                
                # 4. 向下滚动页面，触发内容加载
                print("📜 向下滚动页面，触发内容加载...")
                await page.wait_for_timeout(2000)
                
                for i in range(3):
                    await page.evaluate('window.scrollBy(0, 500)')
                    await page.wait_for_timeout(1000)
                
                print("⏳ 等待页面内容加载...")
                await page.wait_for_timeout(15000)  # 等待 15s 让动态内容加载完成
            
            # 5. 获取新闻列表
            print("\n📋 获取新闻列表...")
            news_data = await page.evaluate('''() => {
                const allLinks = document.querySelectorAll('a[href*="/VIDE"]');
                const results = [];
                const seenUrls = new Set();
                
                allLinks.forEach(link => {
                    const href = link.href;
                    const text = link.textContent.trim();
                    
                    if (!text || text.length < 5) return;
                    
                    const urlParts = href.split('/');
                    let newsDate = '';
                    for (let i = 0; i < urlParts.length - 1; i++) {
                        if (urlParts[i].match(/^\\d{4}$/) && 
                            urlParts[i+1].match(/^\\d{2}$/) && 
                            urlParts[i+2].match(/^\\d{2}$/)) {
                            newsDate = urlParts[i] + urlParts[i+1] + urlParts[i+2];
                            break;
                        }
                    }
                    
                    const urlKey = href.split('?')[0];
                    if (seenUrls.has(urlKey)) return;
                    seenUrls.add(urlKey);
                    
                    results.push({ title: text, url: href, date: newsDate });
                });
                
                return results;
            }''')
            
            print(f"✅ 找到 {len(news_data)} 条新闻")
            
            await browser.close()
            
            return news_data[:Config.MAX_NEWS]
    
    def get_news_detail(self, news_title, detail_url):
        """获取新闻详情和视频 URL"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(detail_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 提取新闻内容
            content = ""
            content_area = soup.select_one('#content_area')
            if content_area:
                paragraphs = content_area.find_all('p')
                if paragraphs:
                    content = '\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                else:
                    content = content_area.get_text(separator='\n', strip=True)
            
            if not content:
                all_text = soup.get_text()
                chinese_paragraphs = re.findall(r'[\u4e00-\u9fff]{10,}', all_text)
                content = '\n'.join(chinese_paragraphs[:10])
            
            # 提取视频 URL
            video_url = None
            
            video_tag = soup.find('video')
            if video_tag:
                video_url = video_tag.get('src') or video_tag.get('data-src')
            
            if not video_url:
                for tag in soup.find_all(['embed', 'iframe']):
                    src = tag.get('src', '') or tag.get('href', '')
                    if 'mp4' in src.lower() or 'video' in src.lower() or 'cctv' in src.lower():
                        video_url = src
                        break
            
            if not video_url:
                for script in soup.find_all('script'):
                    script_text = script.string or ''
                    mp4_links = re.findall(r'["\']([^"\']*\.mp4[^"\']*)["\']', script_text)
                    if mp4_links:
                        video_url = mp4_links[0]
                        break
            
            if not video_url:
                video_url = detail_url
            
            return content, video_url
            
        except Exception as e:
            print(f"❌ 获取新闻详情失败：{e}")
            return "", None
    
    async def run(self, target_date=None, download_videos=True):
        """运行爬虫"""
        print("\n" + "="*60)
        print("📡 阶段 1: 新闻联播视频&文本数据爬取")
        print("="*60)
        
        if download_videos:
            if Config.VIDEOS_RAW.exists():
                for f in Config.VIDEOS_RAW.glob("*"):
                    if f.is_file():
                        f.unlink()
                print(f"🗑️ 已清空 {Config.VIDEOS_RAW} 文件夹")
        
        if Config.ALL_VIDEO_JSON.exists():
            Config.ALL_VIDEO_JSON.unlink()
            print(f"🗑️ 已删除 {Config.ALL_VIDEO_JSON}")
        
        self.dic_all_video = {}
        
        selected_date = self.select_date(target_date)
        
        news_list = await self.crawl_with_playwright(selected_date)
        
        if not news_list:
            print("❌ 未找到新闻")
            return False
        
        # 过滤掉标题包含"完整版 新闻联播"或"完整版《新闻联播》"的数据
        print(f"\n📊 过滤前的新闻数量：{len(news_list)}条")
        filtered_news_list = [
            news for news in news_list 
            if "新闻联播" not in news['title'] or "完整版" not in news['title']
        ]
        if len(filtered_news_list) < len(news_list):
            print(f"🗑️ 已过滤掉 {len(news_list) - len(filtered_news_list)} 条包含'完整版 新闻联播'的数据")
            print(f"📊 过滤后的新闻数量：{len(filtered_news_list)}条")
        news_list = filtered_news_list
        
        # 处理每条新闻
        for index, news in enumerate(news_list, 1):
            news_title = news['title']
            detail_url = news['url']
            news_date = news['date']
            
            print(f"\n[{index}/{len(news_list)}] 处理：{news_title[:40]}")
            
            content, video_url = self.get_news_detail(news_title, detail_url)
            if not content:
                print(f"\n❌ 第 {index} 条无内容，跳过")
                continue
            
            video_downloaded = False
            video_path_str = ""
            
            if download_videos and video_url:
                safe_title = re.sub(r'[<>:"/\\|?*]', '_', news_title)
                video_filename = f"{index}_{safe_title}.mp4"
                video_path = Config.VIDEOS_RAW / video_filename
                from tools.download_utils import download_video
                video_downloaded = download_video(video_url, video_path)
                video_path_str = str(video_path) if video_downloaded else ""
            
            self.dic_all_video[str(index)] = {
                "title": news_title,
                "detail_url": detail_url,
                "content": content,
                "video_url": video_url if video_url else "",
                "video_path": video_path_str,
                "video_downloaded": video_downloaded,
                "crawl_time": datetime.now().isoformat()
            }
            
            save_json(Config.ALL_VIDEO_JSON, self.dic_all_video)
            print(f"✅ 第 {index} 条处理完成")
            time.sleep(2)
        
        print(f"\n✅ 爬虫完成，共 {len(self.dic_all_video)} 条新闻{'（未下载视频）' if not download_videos else ''}")
        return True


# ==================== 主函数 ====================

async def main(date_arg=None):
    """主函数"""
    print("\n" + "="*60)
    print("📺 新闻联播视频爬虫")
    print("="*60)
    
    crawler = XWLBCrawler()
    
    try:
        success = await crawler.run(date_arg)
        if success:
            print("\n✅ 所有任务完成！")
        else:
            print("\n❌ 爬虫失败！")
    except Exception as e:
        print(f"\n❌ 发生错误：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys
    
    date_arg = None
    if len(sys.argv) > 1:
        date_arg = sys.argv[1]
        print(f"📅 指定日期：{date_arg}")
    
    asyncio.run(main(date_arg))
