#!/usr/bin/env python3
"""fetch_news.py - 自动获取新闻联播文字内容（免爬虫版）

数据源: 同花顺财经 stock.10jqka.com.cn（可直接 HTTP 抓取）
备选: 东方财富 caifuhao.eastmoney.com

使用方法:
    # 获取指定日期的新闻（默认昨天）
    python3 scripts/fetch_news.py 20260506
    
    # pipe 给 manual 模式
    python3 scripts/fetch_news.py 20260506 | python3 run.py manual
    
    # 直接输出
    python3 scripts/fetch_news.py

输出格式: "比例% 【领域】新闻内容"
"""

import sys
import re
import urllib.request
from datetime import datetime, timedelta

# 同花顺已知的新闻联播文章 URL 列表
# 从搜索历史中已知的 URL ID
KNOWN_URLS = {
    "20260506": "676485761",
    "20260505": "676452819",
    "20260501": "676439024",
    "20260402": "675732346",
    "20260329": "675616733",
}

# 默认分配比例（按排位递减）
RATIO_MAP = [10, 8, 8, 6, 5, 5, 5, 5, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 3, 3]

# 领域分类关键词（按匹配优先级排序）
DOMAIN_KEYWORDS = [
    ("政治", ["习近平", "总书记", "王沪宁", "李强", "总理", "主席", "委员长", "人大", "政协", "会见", "致信", "回信", "批示", "政党", "外交", "外长"]),
    ("经济", ["经济", "投资", "GDP", "增长", "消费", "外贸", "央行", "财政", "税收", "金融", "贷款", "资金", "项目", "设备", "产业"]),
    ("科技", ["科技", "AI", "人工智能", "机器人", "数据", "数字", "芯片", "创新", "航天", "技术", "出口"]),
    ("民生", ["民生", "就业", "医疗", "教育", "住房", "好房子", "养老", "社保", "交通", "出行", "公园"]),
    ("国际", ["国际", "美国", "欧盟", "日本", "伊朗", "俄罗斯", "联合国", "外交", "大使", "海外", "贸易", "制裁", "冲突", "停火", "和平"]),
    ("法治", ["法治", "司法", "法律", "行政处罚", "法院", "检察", "清理"]),
    ("生态", ["生态", "环境", "绿色", "低碳", "排放", "节能", "监测"]),
    ("文化", ["文化", "体育", "旅游", "娱乐", "电影", "节日", "阅读", "无障碍"]),
    ("三农", ["农业", "农村", "农民", "乡村振兴", "粮食", "草原"]),
    ("天气", ["降雨", "降温", "天气", "台风", "暴雨"]),
    ("区域", ["广西", "浙江", "上海", "海南", "广东", "京津冀", "大湾区", "示范区"]),
]


def get_target_date(date_str=None):
    """获取目标日期 YYYYMMDD"""
    if date_str:
        return date_str.replace("-", "").replace("/", "")
    # 默认取昨天（新闻联播每晚19:00播，第二天早上才可获取）
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%Y%m%d")


def fetch_from_10jqka(date_str):
    """从同花顺财经获取新闻联播要闻"""
    
    # 构建 URL：尝试多个可能的 URL 模式
    urls_to_try = [
        f"https://stock.10jqka.com.cn/{date_str}/c{KNOWN_URLS.get(date_str, '')}.shtml",
        f"https://m.10jqka.com.cn/{date_str}/c{KNOWN_URLS.get(date_str, '')}.shtml",
    ]
    
    # 如果没有已知 ID，尝试搜索
    if date_str not in KNOWN_URLS:
        urls_to_try = [
            f"https://stock.10jqka.com.cn/{date_str}/c{s}.shtml"
            for s in generate_possible_ids(date_str)
        ]
    
    for url in urls_to_try:
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                }
            )
            resp = urllib.request.urlopen(req, timeout=10)
            html = resp.read().decode("utf-8", errors="replace")
            
            # 在 <p> 标签中找数字开头的新闻条目
            items = re.findall(r'<p>\s*(\d+[、.][^<]+)</p>', html)
            
            if items and len(items) >= 5:
                print(f"[fetch] ✅ 从 {url} 获取到 {len(items)} 条新闻", file=sys.stderr)
                # 清理条目
                clean_items = []
                for item in items:
                    text = re.sub(r'^\d+[、.]\s*', '', item).strip()
                    text = re.sub(r'\s*\(央视新闻\)\s*$', '', text).strip()
                    if text and len(text) >= 5:
                        clean_items.append(text)
                return clean_items
        except Exception as e:
            continue
    
    return None


def generate_possible_ids(date_str):
    """生成可能的同花顺文章 ID（纯猜测，不一定对）"""
    # 同花顺的 ID 似乎是基于时间戳生成的
    # 目前没有通用规则，返回空列表（触发搜索）
    return []


def search_fallback(date_str):
    """备选：用 firecrawl 搜索同花顺文章"""
    import json
    
    api_key = "fc-57fc4e91d19a482391c65a6ce52d9bd1"
    year = date_str[:4]
    month = date_str[4:6]
    day = date_str[6:8]
    query = f"{year}年{month}月{day}日 新闻联播 要闻 site:10jqka.com.cn"
    
    data = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        "https://api.firecrawl.dev/v1/search",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    )
    
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        result = json.loads(resp.read())
        
        if result.get("success"):
            for item in result["data"]:
                url = item["url"]
                desc = item.get("description", "")
                if "10jqka" in url:
                    # 从 description 提取
                    items = re.findall(r'\d+[、.][^；;]+', desc)
                    if items and len(items) >= 5:
                        print(f"[fetch] 从搜索缓存获取 {len(items)} 条", file=sys.stderr)
                        clean = [re.sub(r'^\d+[、.]\s*', '', i).strip() for i in items]
                        return clean
                    
                    # 尝试直接抓取页面
                    return fetch_from_10jqka_direct(url)
    except:
        pass
    
    return None


def fetch_from_10jqka_direct(url):
    """直接抓取同花顺页面"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
        
        items = re.findall(r'<p>\s*(\d+[、.][^<]+)</p>', html)
        if items and len(items) >= 5:
            clean = [re.sub(r'^\d+[、.]\s*', '', i).strip() for i in items]
            return clean
    except:
        pass
    return None


def classify_domain(title):
    """根据标题内容智能分类领域"""
    for domain, keywords in DOMAIN_KEYWORDS:
        for kw in keywords:
            if kw in title:
                return domain
    return "综合"


def format_manual_input(items):
    """格式化为 manual 模式需要的输入"""
    lines = []
    for i, text in enumerate(items[:25]):  # 最多25条
        ratio = RATIO_MAP[i] if i < len(RATIO_MAP) else 2
        domain = classify_domain(text)
        lines.append(f"{ratio}% 【{domain}】{text}")
    
    return "\n".join(lines)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None
    date_str = get_target_date(target)
    date_display = f"{date_str[:4]}年{date_str[4:6]}月{date_str[6:8]}日"
    
    print(f"[fetch] 目标日期: {date_display}", file=sys.stderr)
    
    # 先尝试直接抓取同花顺
    items = fetch_from_10jqka(date_str)
    
    # 失败则用搜索备选
    if not items:
        print(f"[fetch] 直接抓取失败，尝试搜索...", file=sys.stderr)
        items = search_fallback(date_str)
    
    if items and len(items) >= 5:
        output = format_manual_input(items)
        print(output)
        print(f"[fetch] ✅ {len(items)} 条新闻就绪，输入 manual 模式", file=sys.stderr)
        return
    
    print(f"[fetch] ❌ 无法获取 {date_str} 的新闻", file=sys.stderr)
    print(f"[fetch] 请手动运行: python3 run.py manual", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
