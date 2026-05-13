"""Panel generator for news video frames.

纵向布局，每页最多5条，逐条渐进显示：
- 画布 1920x1080，深木质色背景 #2d1f16
- 顶部日期标题居中，下方横向细线分隔
- 新闻从上到下纵向排列，一条一行
- 每页最多5条，超5条翻页
- 逐条渐进显示（一条一帧）
"""

import os
import json
import random
from PIL import Image, ImageDraw, ImageFont

import yaml

# ── Config ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

CW = CONFIG["canvas"]["width"]
CH = CONFIG["canvas"]["height"]
BG = CONFIG["canvas"]["background"]

ITEMS_PER_PAGE = 5


def load_font(size, bold=False):
    """Load font, fallback to default if TTC fails."""
    font_path = CONFIG["fonts"]["bold"] if bold else CONFIG["fonts"]["regular"]
    try:
        return ImageFont.truetype(font_path, size)
    except (IOError, OSError):
        try:
            return ImageFont.truetype("msyh.ttc", size)
        except (IOError, OSError):
            return ImageFont.load_default()


def _get_plate_summary(news_items):
    """按"主题概念"(plate) 分组聚合 ratio，过滤掉空 plate，按总 ratio 降序排列。"""
    from collections import defaultdict

    groups = defaultdict(list)
    for item in news_items:
        plate = item.get("plate", "").strip()
        if not plate:
            continue
        groups[plate].append(item)

    result = []
    for plate, items in groups.items():
        total_ratio = sum(item.get("ratio", 0) for item in items)
        result.append({"plate": plate, "total_ratio": total_ratio, "items": items})

    result.sort(key=lambda x: -x["total_ratio"])
    return result


def generate_heatmap(news_items):
    """生成片尾竖状条形图，按主题概念分组展示覆盖占比。"""
    colors = CONFIG["colors"]
    img = Image.new("RGB", (CW, CH), colors["heatmap_bg"])
    draw = ImageDraw.Draw(img)

    plate_stats = _get_plate_summary(news_items)
    if not plate_stats:
        return img

    total_of_all = sum(ps["total_ratio"] for ps in plate_stats)
    if total_of_all == 0:
        total_of_all = 1

    bar_area_left = 120
    bar_area_right = CW - 120
    bar_area_width = bar_area_right - bar_area_left
    bar_area_top = 200
    bar_area_bottom = 800
    bar_area_height = bar_area_bottom - bar_area_top

    count = len(plate_stats)
    max_bars = 10
    count = min(count, max_bars)
    plate_stats = plate_stats[:max_bars]

    gap_ratio = 0.25
    bar_count_with_gap = count + (count - 1) * gap_ratio
    bar_unit_w = bar_area_width / bar_count_with_gap if bar_count_with_gap > 0 else 100
    bar_w = bar_unit_w
    gap_w = bar_unit_w * gap_ratio

    max_ratio = plate_stats[0]["total_ratio"]

    title_font = load_font(56, bold=True)
    title_text = "今日重点覆盖"
    tb = draw.textbbox((0, 0), title_text, font=title_font)
    draw.text(((CW - (tb[2] - tb[0])) // 2, 80), title_text,
              fill="#FFFFFF", font=title_font)

    for i, ps in enumerate(plate_stats):
        x = bar_area_left + i * (bar_w + gap_w)
        bar_h = int(bar_area_height * (ps["total_ratio"] / max_ratio)) if max_ratio > 0 else 0
        bar_y = bar_area_bottom - bar_h

        hue = max(0, min(240, i * 30))
        sat = max(40, 100 - i * 6)
        light = max(40, 60 - i * 3)
        light_dim = max(30, light - 15)

        def _hsl_to_hex(h, s, l):
            s /= 100
            l /= 100
            c = (1 - abs(2 * l - 1)) * s
            x = c * (1 - abs((h / 60) % 2 - 1))
            m = l - c / 2
            if h < 60:     r, g, b = c, x, 0
            elif h < 120:  r, g, b = x, c, 0
            elif h < 180:  r, g, b = 0, c, x
            elif h < 240:  r, g, b = 0, x, c
            else:          r, g, b = x, 0, c
            r, g, b = int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)
            return f"#{r:02x}{g:02x}{b:02x}"

        bar_color = _hsl_to_hex(hue, sat, light)
        bar_color_dim = _hsl_to_hex(hue, sat, light_dim)

        if bar_h > 0:
            draw.rectangle([(x, bar_y), (x + bar_w, bar_area_bottom)],
                           fill=bar_color)
            draw.rectangle([(x, bar_y), (x + bar_w, bar_y + 4)],
                           fill="#FFFFFF", width=0)
            draw.rectangle([(x + bar_w - 3, bar_y), (x + bar_w, bar_area_bottom)],
                           fill=bar_color_dim, width=0)

        pct = ps["total_ratio"] / total_of_all * 100
        pct_text = f"{pct:.0f}%"
        pct_font = load_font(32, bold=True)
        pb = draw.textbbox((0, 0), pct_text, font=pct_font)
        pct_text_w = pb[2] - pb[0]
        draw.text((x + bar_w // 2 - pct_text_w // 2, bar_y - 40),
                  pct_text, fill=bar_color, font=pct_font)

        plate_name = ps["plate"]
        plate_font = load_font(30, bold=(i == 0))
        pb2 = draw.textbbox((0, 0), plate_name, font=plate_font)
        plate_text_w = pb2[2] - pb2[0]
        plate_x = x + bar_w // 2 - plate_text_w // 2

        if plate_x < bar_area_left:
            plate_x = bar_area_left
        if plate_x + plate_text_w > bar_area_right:
            plate_x = bar_area_right - plate_text_w

        draw.text((plate_x, bar_area_bottom + 20),
                  plate_name, fill=bar_color, font=plate_font)

    subtitle_font = load_font(26)
    draw.text((CW // 2 - 200, CH - 50),
              "数据来源：央视新闻联播 | 主题概念按新闻内容自动匹配",
              fill=colors["subtitle"], font=subtitle_font)

    return img


def draw_column_headers(draw, y, left_margin, col_centers):
    """绘制三列表头（居中）。"""
    colors = CONFIG["colors"]
    header_font = load_font(34, bold=True)
    header_color = "#B8860B"

    headers = ["原文占比", "主题概念", "新闻摘要"]
    for i, text in enumerate(headers):
        cx = col_centers[i]
        tb = draw.textbbox((0, 0), text, font=header_font)
        tw = tb[2] - tb[0]
        draw.text((cx - tw // 2, y), text, fill=header_color, font=header_font)

    draw.line([(left_margin, y + 42), (CW - left_margin, y + 42)],
              fill=colors["separator"], width=1)


def draw_item_row(draw, item, y, col_centers, left_margin):
    """绘制单条新闻（三列居中布局）。"""
    colors = CONFIG["colors"]

    col_widths = [140, 200, CW - left_margin * 2 - 140 - 200 - 80]
    remaining_w = col_widths[2]

    ratio_font = load_font(40, bold=False)
    ratio_text = f"{item['ratio']}%"
    tb = draw.textbbox((0, 0), ratio_text, font=ratio_font)
    draw.text((col_centers[0] - (tb[2] - tb[0]) // 2, y + 5),
              ratio_text, fill=colors["timestamp"], font=ratio_font)

    plate_font = load_font(40, bold=True)
    plate = item.get("plate", "").strip()
    plate_text = plate if plate else "—"
    pb = draw.textbbox((0, 0), plate_text, font=plate_font)
    plate_text_w = pb[2] - pb[0]
    if plate_text_w > col_widths[1]:
        cur_size = 40
        while plate_text_w > col_widths[1] and cur_size > 24:
            cur_size -= 2
            plate_font = load_font(cur_size, bold=True)
            pb = draw.textbbox((0, 0), plate_text, font=plate_font)
            plate_text_w = pb[2] - pb[0]
    draw.text((col_centers[1] - plate_text_w // 2, y + 5),
              plate_text, fill=colors["domain_tag"], font=plate_font)

    body_font = load_font(44, bold=False)
    summary = item["summary"]
    current_size = 44
    sb = draw.textbbox((0, 0), summary, font=body_font)
    text_w = sb[2] - sb[0]
    while text_w > remaining_w and current_size > 28:
        current_size -= 2
        body_font = load_font(current_size, bold=False)
        sb = draw.textbbox((0, 0), summary, font=body_font)
        text_w = sb[2] - sb[0]
    draw.text((col_centers[2] - text_w // 2, y + 5),
              summary, fill=colors["body"], font=body_font)


def generate_progressive_panels(news_items, news_date_str):
    """生成渐进式面板帧（纵向逐条显示）。"""
    colors = CONFIG["colors"]
    frames = []

    title_font = load_font(64, bold=True)

    left_margin = 80
    header_y = 140

    col_widths = [140, 200, CW - left_margin * 2 - 140 - 200 - 80]
    col_centers = [
        left_margin + col_widths[0] // 2,
        left_margin + col_widths[0] + 40 + col_widths[1] // 2,
        left_margin + col_widths[0] + 40 + col_widths[1] + 40 + col_widths[2] // 2,
    ]

    content_top = 195
    content_bottom = 980
    content_area_height = content_bottom - content_top

    pages = []
    for i in range(0, len(news_items), ITEMS_PER_PAGE):
        pages.append(news_items[i:i + ITEMS_PER_PAGE])

    total_pages = len(pages)

    for page_idx, page in enumerate(pages):
        items_in_page = len(page)
        row_height = content_area_height // items_in_page
        row_height = min(row_height, 200)

        for reveal_idx in range(items_in_page):
            img = Image.new("RGB", (CW, CH), BG)
            draw = ImageDraw.Draw(img)

            title = f"新闻联播极简摘要  {news_date_str}"
            tb = draw.textbbox((0, 0), title, font=title_font)
            draw.text(((CW - (tb[2] - tb[0])) // 2, 30), title,
                      fill=colors["title"], font=title_font)

            draw.line([(80, 100), (CW - 80, 100)],
                      fill=colors["separator"], width=1)

            draw_column_headers(draw, header_y, left_margin, col_centers)

            for row_idx in range(reveal_idx + 1):
                item = page[row_idx]
                y = content_top + row_idx * row_height + (row_height - 40) // 2
                draw_item_row(draw, item, y, col_centers, left_margin)

            indicator_font = load_font(28)
            indicator = f"{page_idx + 1}/{total_pages}"
            ir = draw.textbbox((0, 0), indicator, font=indicator_font)
            draw.text((CW - 80 - (ir[2] - ir[0]), CH - 50), indicator,
                      fill=colors["subtitle"], font=indicator_font)

            frames.append(img)

    return frames
