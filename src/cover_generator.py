"""Cover image generator for vertical phone layout.

生成手机竖版封面图（1080×1920）：
- 标题下移放大 + 圆形词云居中
- 词云内容按东方财富板块匹配，匹配不到则用标题关键词
- 颜色冷热、字体大小按权重排序
"""

import os
import json
import re
from collections import Counter
from PIL import Image, ImageDraw, ImageFont

import yaml
from wordcloud import WordCloud

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

CW = 1080
CH = 1920
FONT_REGULAR = CONFIG["fonts"]["regular"]
FONT_BOLD = CONFIG["fonts"]["bold"]
DIC_PATH = os.path.join(BASE_DIR, "dic_all_video.json")
PLATE_PATH = os.path.join(BASE_DIR, "assets", "东方财富板块列表.txt")


def load_font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except (IOError, OSError):
        try:
            return ImageFont.truetype("msyh.ttc", size)
        except (IOError, OSError):
            return ImageFont.load_default()


def _extract_date_from_url(url):
    m = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
    if m:
        return f"{m.group(1)}年{m.group(2)}月{m.group(3)}日"
    return ""


def _load_plate_list():
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


def _extract_topics():
    """从新闻中提取主题概念。"""
    if not os.path.exists(DIC_PATH):
        print("[ERROR] dic_all_video.json not found")
        return "", []

    with open(DIC_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    first_key = sorted(data.keys(), key=lambda k: int(k) if k.isdigit() else 0)[0]
    detail_url = data[first_key].get("detail_url", "")
    news_date = _extract_date_from_url(detail_url)

    keys = sorted(data.keys(), key=lambda k: int(k) if k.isdigit() else 0)
    plates = _load_plate_list()

    SECTION_TOPIC = {
        "在希望的田野上": "粮食生产",
        "劳动者之歌": "盐湖科考",
        "实干笃行创伟业 团结奋斗新征程": "重大工程",
    }

    topic_weights = Counter()

    for key in keys:
        item = data[key]
        title = item.get("title", "")
        content = item.get("content", "")
        clen = len(content)

        clean_title = re.sub(r'^完整版\[视频\]', '', title)

        matched_plate = ""
        for plate in plates:
            if plate in clean_title:
                if len(plate) > len(matched_plate):
                    matched_plate = plate

        if matched_plate:
            topic_weights[matched_plate] += clen * 3
            continue

        content_matched = ""
        for plate in plates:
            if len(plate) < 3:
                continue
            if plate in content:
                count_in_content = content.count(plate)
                if len(plate) <= 4 and count_in_content < 2:
                    continue
                if len(plate) > len(content_matched):
                    content_matched = plate

        if content_matched:
            topic_weights[content_matched] += int(clen * 0.5)
            continue

        brackets = re.findall(r'【(.+?)】', clean_title)
        used = False
        for b in brackets:
            b = b.strip()
            if b in SECTION_TOPIC:
                topic_weights[SECTION_TOPIC[b]] += clen
                used = True
                break
            elif len(b) >= 2 and "联播快讯" not in b and "国际" not in b:
                topic_weights[b] += int(clen * 0.8)
                used = True
                break

        if used:
            continue

        title_parts = clean_title
        for name in ["习近平", "总书记", "李强", "张国清"]:
            title_parts = title_parts.replace(name, "")
        title_parts = re.sub(r'【.+?】', '', title_parts)

        title_parts = re.sub(r'[，。！？；：\s"]+', '|', title_parts)
        segments = [s.strip() for s in title_parts.split('|') if s.strip()]

        skip_prefixes = [
            "对", "抓好", "加强", "作出重要指示", "作出重要指示强调",
            "作出批示", "确保", "强调", "要求", "表示",
        ]
        exclude_keywords = {
            "新闻联播", "国内联播快讯", "国际联播快讯",
            "二十四节气", "立夏", "国际",
        }

        used = False
        for seg in segments:
            if any(ek in seg for ek in exclude_keywords):
                continue

            starts_with_prefix = False
            for sp in skip_prefixes:
                if seg.startswith(sp):
                    starts_with_prefix = True
                    break

            if len(seg) >= 3:
                if seg[0] in "的了在我有和就不对将以为了" and not starts_with_prefix:
                    continue
                seg = re.sub(r'^[的了在我有还暨与及届]', '', seg)
                if len(seg) < 3:
                    continue
                action_cut = re.search(r'(.+?)(?:作出|强调|要求|指出|表示|批示)', seg)
                if action_cut:
                    seg = action_cut.group(1).strip()
                admin_suffixes = "省|市|县|区|镇|乡|村"
                place_match = re.search(r'(?:' + admin_suffixes + r')[的]?([\u4e00-\u9fff]{3,})', seg)
                if place_match:
                    place_char = place_match.group(0)[0]
                    prev_char = seg[place_match.start()-1] if place_match.start() > 0 else ""
                    if place_char == "市" and prev_char in "城都品区镇县":
                        pass
                    elif place_char == "区" and prev_char in "社地街":
                        pass
                    else:
                        seg = place_match.group(1)
                seg = re.sub(r'^\d+届?', '', seg)
                seg = re.sub(r'^[一第对在从将]', '', seg)
                if len(seg) > 10:
                    seg = re.sub(r'^[美伊俄德法英][^，。！？；：]{0,4}[称说表]', '', seg)
                    seg = re.sub(r'^[对在从第将]', '', seg)
                    seg = re.sub(r'^\d+届?', '', seg)
                    if len(seg) > 8:
                        seg = seg[:8]
                    seg = re.sub(r'(击沉|[的了在着过和与及击今昨加])$', '', seg)
                if len(seg) >= 3:
                    topic_weights[seg] += int(clen * 0.6)
                    used = True
                    break

    if not topic_weights:
        return news_date, [("新闻联播", 100)]

    sorted_t = sorted(topic_weights.items(), key=lambda x: -x[1])[:10]
    mv = sorted_t[0][1]
    result = [(k, max(1, int(v / mv * 100))) for k, v in sorted_t]

    print(f"  → 提取到 {len(result)} 个主题概念")
    for i, (k, v) in enumerate(result, 1):
        print(f"    {i}. {k} (权重={v})")
    return news_date, result


def _generate_circular_wordcloud(keywords):
    weight_dict = {k: v for k, v in keywords}

    def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        ratio = weight_dict.get(word, 50) / 100.0
        hue = int(240 * (1 - ratio))
        sat = 80 + int(20 * ratio)
        light = 50 + int(20 * (1 - ratio))
        return f"hsl({hue}, {sat}%, {light}%)"

    wc = WordCloud(
        font_path=FONT_REGULAR,
        width=700,
        height=700,
        background_color=None,
        mode="RGBA",
        color_func=color_func,
        max_words=10,
        max_font_size=140,
        min_font_size=36,
        prefer_horizontal=0.6,
        random_state=42,
        margin=15,
        collocations=False,
        relative_scaling=0.5,
    )
    wc.generate_from_frequencies(weight_dict)
    wc_img = wc.to_image()

    mask = Image.new("L", wc_img.size, 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse([(0, 0), wc_img.size], fill=255)

    result = Image.new("RGBA", wc_img.size, (0, 0, 0, 0))
    result.paste(wc_img, (0, 0), mask)
    return result


def draw_gradient_bg(draw, w, h):
    for y in range(h):
        r = y / h
        rv = int(13 + (26 - 13) * r)
        gv = int(17 + (27 - 17) * r)
        bv = int(23 + (46 - 23) * r)
        draw.line([(0, y), (w, y)], fill=(rv, gv, bv))


def draw_cover(topics, date_str):
    img = Image.new("RGB", (CW, CH), "#0D1117")
    draw = ImageDraw.Draw(img)
    draw_gradient_bg(draw, CW, CH)

    wc_size = 700
    title_block_h = 40 + 20 + 80 + 25 + 700 + 30
    base_y = (CH - title_block_h) // 2

    draw.rectangle([(0, 0), (6, base_y + 165)], fill="#FF6B35")

    sf = load_font(34, bold=False)
    draw.text((60, base_y), "新闻联播", fill="#FF6B35", font=sf)

    tf = load_font(64, bold=True)
    title = f'{date_str}《新闻联播》速览'
    tb = draw.textbbox((0, 0), title, font=tf)
    tw = tb[2] - tb[0]
    if tw > CW - 120:
        for sz in range(64, 36, -2):
            tf = load_font(sz, bold=True)
            tb = draw.textbbox((0, 0), title, font=tf)
            tw = tb[2] - tb[0]
            if tw <= CW - 120:
                break
    draw.text(((CW - tw) // 2, base_y + 60), title, fill="#FFFFFF", font=tf)

    draw.line([(CW // 2 - 200, base_y + 145), (CW // 2 + 200, base_y + 145)], fill="#FF6B35", width=2)

    wc_img = _generate_circular_wordcloud(topics)
    wc_x = (CW - wc_size) // 2
    wc_y = base_y + 170
    img.paste(wc_img, (wc_x, wc_y), wc_img)

    bf = load_font(22, bold=False)
    bt = "数据来源：央视《新闻联播》"
    bb = draw.textbbox((0, 0), bt, font=bf)
    draw.text(((CW - (bb[2] - bb[0])) // 2, CH - 60), bt, fill="#555566", font=bf)

    return img


def generate_cover(output_dir=None, target_date_str=None, news_items=None):
    """生成封面的生产接口，供 run.py 调用。"""
    if news_items is not None:
        from collections import Counter
        from datetime import datetime
        _get_today = lambda: f"{datetime.now().year}年{datetime.now().month:02d}月{datetime.now().day:02d}日"
        plates = _load_plate_list()
        topic_weights = Counter()
        for item in news_items:
            summary = item.get("summary", "")
            ratio = item.get("ratio", 1)
            plate = item.get("plate", "")
            if plate:
                topic_weights[plate] += ratio * 3
            else:
                for p in plates:
                    if p in summary:
                        if len(p) > 3 or summary.count(p) >= 1:
                            topic_weights[p] += ratio
                            break
                else:
                    kw = summary[:6].rstrip("的着了过和与及")
                    if len(kw) >= 3:
                        topic_weights[kw] += ratio
        if not topic_weights:
            topic_weights["新闻联播"] = 100
        sorted_t = sorted(topic_weights.items(), key=lambda x: -x[1])[:10]
        mv = sorted_t[0][1]
        topics = [(k, max(1, int(v / mv * 100))) for k, v in sorted_t]
        news_date = _get_today() if not target_date_str else \
            f"{target_date_str[:4]}年{target_date_str[4:6]}月{target_date_str[6:8]}日"
    else:
        news_date, topics = _extract_topics()
        if not topics:
            print("[ERROR] 未提取到主题概念")
            return None

    m = re.search(r'(\d{4})年(\d{2})月(\d{2})日', news_date)
    ymd = m.group(1) + m.group(2) + m.group(3) if m else "unknown"

    cover_img = draw_cover(topics, news_date)

    if output_dir is None:
        panel_dir = os.path.join(BASE_DIR, "output", "panels")
        output_dir = os.path.join(panel_dir, ymd)
    os.makedirs(output_dir, exist_ok=True)

    cover_path = os.path.join(output_dir, "cover.png")
    cover_img.save(cover_path)

    txt_path = os.path.join(output_dir, "cover_keywords.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"封面日期: {news_date}\n")
        f.write("主题概念(按权重排序):\n")
        for i, (kw, wt) in enumerate(topics, 1):
            f.write(f"  {i}. {kw} (权重={wt})\n")

    return {
        "cover_path": cover_path,
        "topics": topics,
        "news_date": news_date,
        "date_str": ymd,
    }
