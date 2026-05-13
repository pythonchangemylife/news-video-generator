"""News extraction and LLM analysis module."""

import os
import json
import re
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIC_PATH = os.path.join(BASE_DIR, "dic_all_video.json")
PLATE_PATH = os.path.join(BASE_DIR, "assets", "东方财富板块列表.txt")


def _extract_date_from_url(url):
    """从 URL 中提取 YYYYMMDD 格式日期"""
    m = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if m:
        return f"{m.group(1)}年{m.group(2)}月{m.group(3)}日"
    return ""


def _load_plate_list():
    """加载东方财富板块列表."""
    plates = []
    try:
        with open(PLATE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    plates.append(line)
    except (FileNotFoundError, IOError):
        pass
    return plates


def _load_dic_data():
    """读取 dic_all_video.json 并提取日期"""
    if not os.path.exists(DIC_PATH):
        print(f"[ERROR] {DIC_PATH} not found")
        return {}, ""

    with open(DIC_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    news_date = ""
    first_key = sorted(data.keys(), key=lambda k: int(k) if k.isdigit() else 0)[0]
    first_item = data[first_key]
    detail_url = first_item.get("detail_url", "")
    news_date = _extract_date_from_url(detail_url)

    return data, news_date


def _build_raw_text(data):
    """将 JSON 数据拼接成原始文本"""
    lines = []
    keys = sorted(data.keys(), key=lambda k: int(k) if k.isdigit() else 0)

    for key in keys:
        item = data[key]
        title = item.get("title", "")
        content = item.get("content", "")
        if len(content) > 600:
            content = content[:600]
        lines.append(f"【{title}】\n{content}")

    return "\n\n".join(lines)


def _call_llm(prompt):
    """调用 DeepSeek API."""
    import requests

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        env_path = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEEPSEEK_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip("\"'")
                        break
    if not api_key:
        print("[ERROR] DEEPSEEK_API_KEY 未设置")
        return ""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    try:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
            proxies={"http": "", "https": ""}
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return content
    except Exception as e:
        print(f"[ERROR] LLM call failed: {e}")
        return ""


def _parse_analysis(text):
    """解析 LLM 返回的 JSON 数组"""
    json_match = re.search(r'\[.*?\]', text, re.DOTALL)
    if not json_match:
        print("[ERROR] No JSON found in LLM response")
        return []

    try:
        items = json.loads(json_match.group())
        valid = []
        for item in items:
            if all(k in item for k in ("domain", "summary", "time", "ratio")):
                item.setdefault("plate", "")
                valid.append(item)
        return valid
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON parse error: {e}")
        return []


def _build_prompt(raw_text, plates):
    """构建 LLM 分析 prompt."""
    plates_str = "\n".join(plates) if plates else "无历史板块数据"

    prompt = f"""你是一个专业的新闻分析助手。请分析以下央视《新闻联播》全文，提取新闻要素。

要求：
1. 将完整版(视频)[xxx]标题中的"完整版"前缀去掉
2. 总结每条新闻（20-40字，保留数字和关键信息）
3. 标注新闻领域(domain)，取值：经济、民生、科技、外交、军事、文化、社会、体育、环保、能源、工业、农业、外贸、金融、教育
4. 标注时间(time)：每条统一用"19:00"（保留字段用于后续处理）
5. 标注占比(ratio)：根据新闻在全文中的重要程度给 1-100 的整数分值，原文占比越高分值越大
6. 标注主题概念(plate)：对照以下东方财富板块列表，选择最匹配的主题概念。**宁可留空也不要强行匹配**——如果新闻内容与板块列表中任何概念都不明显相关，则将 plate 设为空字符串 ""。
7. 以下是东方财富板块列表（仅从其中挑选）：

{plates_str}

8. **敏感内容过滤**：如果新闻内容涉及以下任一敏感类别，请将整条新闻从输出中剔除（不输出该条）：
   - 政治敏感内容（领导人负面、政策争议、群体性事件、意识形态争议等）
   - 社会敏感事件（重大安全事故、灾难的具体伤亡细节、社会骚乱等）
   - 涉密信息（军事部署细节、未公开的统计数据等）
   对于不涉及核心敏感但提到相关词汇的新闻，进行**脱敏处理**（如将具体伤亡人数改为"造成伤亡"，将具体地名改为"某地"）。

9. **商业关联度筛选**：只保留与商业投资存在明显关联的新闻。以下类型的新闻应当剔除：
   - 单纯的外交礼节性活动（会见、出访无实质经贸内容）
   - 纯粹的体育赛事报道（无商业赞助或产业关联）
   - 单纯的文化娱乐活动（无文旅消费或产业联动）
   - 单纯的人事任免
   - 领导人一般性调研视察（无重大政策信号或产业影响）
   - 灾情报道（已做脱敏处理后,若有重建/保险/基建投资关联可保留）
   - 国际新闻中与中国的商业/贸易/投资无关的部分

   应保留的新闻类型（与商业投资明显相关）：
   - 经济数据、政策出台、产业规划
   - 重大工程项目、基础设施建设
   - 科技创新、产业突破
   - 金融市场动态、外贸数据
   - 消费市场数据、文旅产业
   - 能源、工业、农业等实体经济相关
   - 区域经济发展、营商环境
   - 外资外贸、国际合作中有实质商业内容

请严格按照以下 JSON 格式输出（不要额外说明）：
[
  {{"domain": "经济", "summary": "假期前两日全国78个步行街商圈客流量营业额同比增5.4%和5.1%", "time": "19:00", "ratio": 12, "plate": "旅游酒店"}},
  ...
]

新闻全文：
{raw_text}"""

    return prompt


def extract_news_items():
    """主入口：读取 JSON → LLM 分析 → 返回结构化新闻列表。"""
    print(f"\n[Step 1] 读取 {os.path.basename(DIC_PATH)}...")
    data, news_date = _load_dic_data()

    if not data:
        print(f"[ERROR] No data in {DIC_PATH}")
        return [], ""

    raw_text = _build_raw_text(data)
    print(f"[OK] 共 {len(data)} 条新闻，正文总计 {len(raw_text)} 字，日期={news_date}")

    plates = _load_plate_list()
    if not plates:
        print(f"[WARN] 未加载到板块列表")

    prompt = _build_prompt(raw_text, plates)
    print(f"[Step 2] LLM 分析全文 ({len(raw_text)} 字)...")

    llm_output = _call_llm(prompt)
    if not llm_output:
        print("[ERROR] LLM returned empty")
        return [], news_date

    items = _parse_analysis(llm_output)
    if not items:
        print("[ERROR] Failed to parse LLM output")
        return [], news_date

    items = [it for it in items if it.get("summary", "").strip()]

    low_biz_domains = {"外交", "军事", "文化", "体育", "社会"}
    filtered = []
    for item in items:
        domain = item.get("domain", "")
        summary = item.get("summary", "")
        if domain in low_biz_domains:
            biz_keywords = ["经贸", "投资", "贸易", "合作", "产业", "消费",
                            "旅游", "票房", "经济", "商业", "市场", "出口",
                            "进口", "增长", "项目", "建设"]
            if not any(kw in summary for kw in biz_keywords):
                print(f"  [过滤] 低商业关联: [{domain}] {summary[:30]}...")
                continue
        filtered.append(item)
    items = filtered

    return items, news_date


def parse_manual_news(raw_text):
    """手动输入解析（适用于 cmd_manual）。"""
    lines = raw_text.strip().split("\n")
    items = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = re.match(
            r'(?:\d{1,2}:\d{2}\s+)?(\d+)%\s+【(.+?)】(.+)',
            line
        )
        if m:
            items.append({
                "domain": m.group(2),
                "summary": m.group(3).strip(),
                "time": "19:00",
                "ratio": int(m.group(1)),
                "plate": "",
            })
        else:
            items.append({
                "domain": "综合",
                "summary": line[:60],
                "time": "19:00",
                "ratio": 10,
                "plate": "",
            })
    return items


def _get_sample_news():
    """生成测试用样例数据。"""
    return [
        {"domain": "经济", "summary": "假期前两日全国78个步行街商圈客流量营业额同比增5.4%和5.1%",
         "time": "19:00", "ratio": 12, "plate": "旅游酒店"},
        {"domain": "经济", "summary": "2026年消费品以旧换新惠及8427.4万人次带动销售额6193.6亿",
         "time": "19:00", "ratio": 10, "plate": "大消费"},
        {"domain": "民生", "summary": "预计5月3日全社会跨区域人员流动量超2.9亿人次同比增长2.5%",
         "time": "19:00", "ratio": 9, "plate": "旅游酒店"},
        {"domain": "科技", "summary": "神舟二十一号乘组在轨驻留满六个月进行脑电测试等多项实验",
         "time": "19:00", "ratio": 8, "plate": "航天航空"},
        {"domain": "文化", "summary": "2026上海国际花卉节举办花草走出植物园融入城市成为人民大花园",
         "time": "19:00", "ratio": 6, "plate": "美丽中国"},
        {"domain": "外贸", "summary": "第139届广交会已吸引154个境外工商机构团组参加同比增长16.7%",
         "time": "19:00", "ratio": 5, "plate": "外贸"},
        {"domain": "外交", "summary": "中国外交部就东京审判80周年表示日本右翼加速再军事化",
         "time": "19:00", "ratio": 5, "plate": "军工"},
        {"domain": "工业", "summary": "石油化工行业工业智能体烽火正式发布可直接参与生产作业",
         "time": "19:00", "ratio": 4, "plate": "人工智能"},
        {"domain": "科技", "summary": "我国已建成高质量数据集超11.6万个总体量超960拍字节",
         "time": "19:00", "ratio": 4, "plate": "东数西算"},
        {"domain": "文化", "summary": "五一档电影票房突破5亿元全产业链产值近78亿元",
         "time": "19:00", "ratio": 4, "plate": "影视概念"},
    ]


def generate_title(news_date, main_keyword):
    """生成标题，支持 A/B 测试探索标题。"""
    import yaml
    config_path = os.path.join(BASE_DIR, "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    ab = config.get("ab_test", {})
    exploration_rate = ab.get("exploration_rate", 0.1)
    main_template = ab.get("main_template", "{YYYY年MM月DD日}新闻联播摘要：{keyword}")
    explore_templates = ab.get("explore_templates", [])

    m = re.match(r'(\d{4})年(\d{2})月(\d{2})日', news_date)
    if m:
        yyyy = m.group(1)
        mm = m.group(2)
        dd = m.group(3)
    else:
        yyyy, mm, dd = "2026", "05", "01"

    is_exploration = random.random() < exploration_rate

    if is_exploration and explore_templates:
        template = random.choice(explore_templates)
        title = template.replace("{YYYY年MM月DD日}", news_date) \
                        .replace("{keyword}", main_keyword)
    else:
        title = main_template.replace("{YYYY年MM月DD日}", news_date) \
                             .replace("{keyword}", main_keyword)

    return title, is_exploration


def get_main_keyword(news_items):
    """从新闻列表中提取主要关键词（用于标题）。"""
    if not news_items:
        return "新闻"

    from collections import Counter
    domain_ratios = Counter()
    for item in news_items:
        domain_ratios[item["domain"]] += item.get("ratio", 1)

    top_domain = domain_ratios.most_common(1)[0][0]
    return top_domain


def get_today_date():
    """获取今天日期字符串。"""
    from datetime import datetime
    now = datetime.now()
    return f"{now.year}年{now.month:02d}月{now.day:02d}日"
