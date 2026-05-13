#!/usr/bin/env python3
"""News Video Generator - One-click entry point.

Usage:
    python run.py daily              # Full daily pipeline (fetch → generate)
    python run.py daily YYYYMMDD     # Fetch & generate for specific date
    python run.py recompose YYYYMMDD # Re-compose video from existing frames
    python run.py test               # Test panel generation only
    python run.py manual             # Input news text manually, then generate
    python run.py backfill           # Check videos due for 48h metrics backfill
    python run.py schedule           # Start the daily scheduler
"""

import os
import sys
import uuid
import logging
import re
from datetime import datetime

import yaml
import schedule
import time

# Add src to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.panel_generator import generate_heatmap, generate_progressive_panels
from src.news_extractor import (
    extract_news_items,
    parse_manual_news,
    generate_title,
    get_main_keyword,
    get_today_date,
)
from src.video_composer import generate_voiceover_sync, compose_video
from src.data_logger import init_db, log_publish, get_pending_metrics_videos
from src.cover_generator import generate_cover


# Config
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

# Logging
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, CONFIG["logging"].get("level", "INFO")),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, CONFIG["logging"].get("file", "logs/app.log")), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def ensure_dirs():
    """Create all required directories."""
    dirs = ["data", "logs"]
    for d in dirs:
        os.makedirs(os.path.join(BASE_DIR, d), exist_ok=True)


def _extract_ymd_from_json_or_date(news_date):
    """从 dic_all_video.json 的 URL 中提取 YYYYMMDD，失败则从 news_date 解析。"""
    _dic_path = os.path.join(BASE_DIR, "dic_all_video.json")
    _ymd = ""
    if os.path.exists(_dic_path):
        import json as _json
        try:
            with open(_dic_path, "r", encoding="utf-8") as _f:
                _data = _json.load(_f)
            _first_key = sorted(_data.keys(), key=lambda k: int(k) if k.isdigit() else 0)[0]
            _first_url = _data[_first_key].get("detail_url", "")
            _m = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', _first_url)
            if _m:
                _ymd = _m.group(1) + _m.group(2) + _m.group(3)
        except Exception:
            pass
    if not _ymd:
        _parts = news_date.replace("年", "-").replace("月", "-").replace("日", "").split("-")
        _ymd = "".join(z.strip().zfill(2) if i > 0 else z.strip() for i, z in enumerate(_parts))
    return _ymd


def _save_info_txt(output_dir, news_date, title):
    """Write info.txt with display title and tags."""
    txt_path = os.path.join(output_dir, "info.txt")
    date_for_title = news_date.replace("年", "").replace("月", "").replace("日", "")
    display_title = f"{date_for_title}《新闻联播》极速播报版"
    tags = "新闻联播、商机、新闻热点"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"{display_title}\n")
        f.write(f"{tags}\n")
    logger.info(f"  → Info txt saved: {txt_path}")
    return txt_path


def _log_to_db(news_date, title, main_keyword, video_path, video_id, is_exploration):
    """Log video publication to SQLite database."""
    logger.info("Logging to database...")
    log_publish(
        video_id=video_id,
        news_date=news_date,
        title=title,
        main_topic=main_keyword,
        is_exploration=is_exploration,
        video_path=video_path,
        content_type="summary",
        title_template="explore" if is_exploration else "main",
    )
    logger.info("  → Publication logged to SQLite")


def _generate_assets(news_items, news_date, output_dir):
    """Generate all visual/audio assets and return them for video composition.

    Args:
        news_items: list[dict] - parsed news items
        news_date: str - date string like "2026年05月06日"
        output_dir: str - output directory path

    Returns:
        dict with keys: panel_frames, heatmap_img, voice_path, cover_result, title, is_exploration, main_keyword
    """
    # Step 3: Generate title
    logger.info("Step 3/6: Generating title...")
    main_keyword = get_main_keyword(news_items)
    title, is_exploration = generate_title(news_date, main_keyword)
    logger.info(f"  → Title: {title} (exploration={is_exploration})")

    # Step 4: Generate panels (progressive reveal with multi-page)
    logger.info("Step 4/6: Generating progressive panels...")
    panel_frames = generate_progressive_panels(news_items, news_date)
    for idx, frame in enumerate(panel_frames):
        frame_path = os.path.join(output_dir, f"panel_{idx+1}.png")
        frame.save(frame_path)
    logger.info(f"  → {len(panel_frames)} progressive panel frames saved ({len(news_items)} items)")

    heatmap_img = generate_heatmap(news_items)
    heatmap_path = os.path.join(output_dir, "heatmap.png")
    heatmap_img.save(heatmap_path)
    logger.info(f"  → Heatmap saved: {heatmap_path}")

    # Step 4b: Generate cover image (vertical phone layout with word cloud)
    logger.info("Step 4b/6: Generating cover image...")
    try:
        ymd = _extract_ymd_from_json_or_date(news_date)
        cover_result = generate_cover(output_dir=output_dir, target_date_str=ymd, news_items=news_items)
        if cover_result:
            logger.info(f"  → Cover saved: {cover_result['cover_path']}")
            logger.info(f"  → Topics: {[t[0] for t in cover_result['topics']]}")
        else:
            logger.warning("  → Cover generation returned no result")
    except Exception as e:
        logger.error(f"  → Cover generation failed: {e}")
        cover_result = None

    # Step 5: Generate voiceover
    logger.info("Step 5/6: Generating voiceover...")
    voice_path = os.path.join(output_dir, "voiceover.mp3")
    try:
        generate_voiceover_sync(news_items, voice_path)
        logger.info(f"  → Voiceover saved: {voice_path}")
    except Exception as e:
        logger.error(f"  → Voiceover generation failed: {e}")
        voice_path = ""

    return {
        "panel_frames": panel_frames,
        "heatmap_img": heatmap_img,
        "voice_path": voice_path,
        "cover_result": cover_result,
        "title": title,
        "is_exploration": is_exploration,
        "main_keyword": main_keyword,
    }


def _compose_video_and_finalize(panel_frames, heatmap_img, voice_path, output_dir, news_date, title,
                                 main_keyword, video_id, is_exploration):
    """Synthesize video from assets, write info.txt, and log to DB.

    Returns:
        video_path: str or False
    """
    # Step 6: Compose video
    logger.info("Step 6/6: Composing video...")
    video_path = os.path.join(output_dir, "news_video.mp4")
    try:
        compose_video(panel_frames, heatmap_img, voice_path, "", video_path)
        logger.info(f"  → Video saved: {video_path}")
    except Exception as e:
        logger.error(f"  → Video composition failed: {e}")
        return False

    # Write info txt
    _save_info_txt(output_dir, news_date, title)

    # Log to database
    _log_to_db(news_date, title, main_keyword, video_path, video_id, is_exploration)

    logger.info("=" * 50)
    logger.info(f"Pipeline complete! Video: {video_path}")
    logger.info(f"Title: {title}")
    logger.info(f"News date: {news_date}")
    logger.info("=" * 50)

    return video_path


def run_daily_pipeline(target_date_str=None, news_items=None):
    """Run the full daily news video generation pipeline.

    Args:
        target_date_str: 目标日期 YYYYMMDD 字符串（仅用于传给 crawler.py），
                         None 表示爬取当天
        news_items: 可选，直接传入已解析的新闻列表。传入则跳过 extract_news_items() 读取步骤。

    Returns:
        video_path: str or False
    """
    logger.info("=" * 50)
    logger.info("Starting daily news pipeline...")
    ensure_dirs()
    init_db()

    if news_items is not None:
        # 使用传入的 news_items，跳过文件读取
        logger.info("Step 1-2: Using provided news_items (skip file read)")
        news_date = get_today_date()
    else:
        # Step 1 & 2: 读取 dic_all_video.json + LLM 分析
        logger.info("Step 1-2: Extracting news from dic_all_video.json...")
        news_items, news_date = extract_news_items()

    if not news_items:
        logger.error("No news items available. Aborting.")
        return False

    logger.info(f"  → 共 {len(news_items)} 条新闻")
    for item in news_items:
        logger.info(f"  [{item['domain']}] {item['time']} {item['ratio']}%: {item['summary']}")

    # Extract YYYYMMDD date for folder structure
    _ymd = _extract_ymd_from_json_or_date(news_date)
    video_id = f"news_{_ymd}_{uuid.uuid4().hex[:6]}"

    # All output files go into a single date folder: output/YYYYMMDD/
    date_str = _ymd
    output_dir = os.path.join(BASE_DIR, "output", date_str)
    os.makedirs(output_dir, exist_ok=True)

    # Generate all assets
    assets = _generate_assets(news_items, news_date, output_dir)

    # Compose video & finalize
    return _compose_video_and_finalize(
        panel_frames=assets["panel_frames"],
        heatmap_img=assets["heatmap_img"],
        voice_path=assets["voice_path"],
        output_dir=output_dir,
        news_date=news_date,
        title=assets["title"],
        main_keyword=assets["main_keyword"],
        video_id=video_id,
        is_exploration=assets["is_exploration"],
    )


def cmd_daily():
    """Daily pipeline.
    用法: python run.py daily [YYYYMMDD]
    """
    import io
    import asyncio
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    from crawler import XWLBCrawler

    target_date = sys.argv[2] if len(sys.argv) > 2 else None
    if target_date:
        target_date = target_date.replace("-", "").replace("/", "")
        if len(target_date) != 8 or not target_date.isdigit():
            logger.warning(f"日期格式无效: {target_date}，使用当天日期")
            target_date = None
        else:
            logger.info(f"爬取指定日期: {target_date}")

    # Step 0: Run crawler first
    logger.info("Step 0: Running crawler to fetch news data...")
    crawler = XWLBCrawler()
    try:
        success = asyncio.run(crawler.run(target_date=target_date, download_videos=False))
        if not success:
            logger.error("Crawler failed. Aborting.")
            return
    except Exception as e:
        logger.error(f"Crawler error: {e}")
        return

    # Run pipeline (reads from dic_all_video.json)
    run_daily_pipeline()


def cmd_recompose():
    """Re-compose video from existing frames in output/YYYYMMDD/.
    用法: python run.py recompose YYYYMMDD
    """
    if len(sys.argv) < 3:
        logger.error("请指定日期: python run.py recompose YYYYMMDD")
        return

    date_str = sys.argv[2].replace("-", "").replace("/", "")
    if len(date_str) != 8 or not date_str.isdigit():
        logger.error(f"日期格式无效: {date_str}")
        return

    output_dir = os.path.join(BASE_DIR, "output", date_str)
    if not os.path.isdir(output_dir):
        logger.error(f"目录不存在: {output_dir}")
        return

    logger.info(f"Re-composing video from: {output_dir}")

    # Load panel frames
    from PIL import Image
    panel_frames = []
    i = 1
    while True:
        path = os.path.join(output_dir, f"panel_{i}.png")
        if not os.path.exists(path):
            break
        panel_frames.append(Image.open(path).copy())
        i += 1

    if not panel_frames:
        logger.error("No panel frames found. Aborting.")
        return

    # Load heatmap
    heatmap_path = os.path.join(output_dir, "heatmap.png")
    if os.path.exists(heatmap_path):
        heatmap_img = Image.open(heatmap_path).copy()
    else:
        logger.warning("No heatmap found, creating blank placeholder")
        heatmap_img = Image.new("RGB", (1920, 1080), "#0D1117")

    # Voiceover
    voice_path = os.path.join(output_dir, "voiceover.mp3")
    if not os.path.exists(voice_path):
        logger.warning("No voiceover found, video will be silent")
        voice_path = ""

    # Remove old video if exists
    video_path = os.path.join(output_dir, "news_video.mp4")
    if os.path.exists(video_path):
        os.remove(video_path)
        logger.info("  → Removed old video file")

    # Compose using ffmpeg directly for reliability
    import subprocess
    n_frames = len(panel_frames)
    heatmap_duration = 2.0  # seconds

    # Get voiceover duration
    voice_duration = 0
    if voice_path:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", voice_path],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                voice_duration = float(result.stdout.strip())
        except Exception:
            pass

    if voice_duration > heatmap_duration:
        panel_duration = (voice_duration - heatmap_duration) / n_frames
    else:
        panel_duration = 0.5

    panel_duration = max(0.2, panel_duration)
    logger.info(f"[sync] {n_frames} 帧, 每帧 {panel_duration:.2f}s, 配音 {voice_duration:.1f}s")

    # Build ffmpeg command
    heatmap_frames = max(1, int(heatmap_duration * 24))  # 24 fps

    cmd = [
        "ffmpeg", "-y",
        "-framerate", f"{1/panel_duration:.6f}",
        "-start_number", "1",
        "-i", os.path.join(output_dir, "panel_%d.png"),
    ]

    if voice_path:
        cmd.extend(["-i", voice_path])

    # Add heatmap as an image input
    cmd.extend(["-i", heatmap_path])

    # Filter: concat panels + heatmap
    scale = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    heatmap_loop_dur = max(1, voice_duration - n_frames * panel_duration) if voice_duration > 0 else 2.0
    heatmap_loop_count = max(1, int(heatmap_loop_dur * 24))

    filter_complex = (
        f"[0:v]{scale}[panels];"
        f"[2:v]{scale},loop=loop={heatmap_loop_count}:size=1:start=0[heatmap];"
        f"[panels][heatmap]concat=n=2:v=1:a=0[outv]"
    )

    map_args = ["-map", "[outv]"]
    if voice_path:
        map_args.extend(["-map", "1:a"])

    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(map_args)
    cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "23"])
    cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    cmd.extend(["-shortest", video_path])

    logger.info(f"Running ffmpeg composition...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg failed: {e.stderr.decode('utf-8', errors='replace')[:500]}")
        return
    except FileNotFoundError:
        logger.error("ffmpeg not found. Falling back to moviepy...")
        try:
            compose_video(panel_frames, heatmap_img, voice_path, "", video_path)
        except Exception as e:
            logger.error(f"moviepy composition also failed: {e}")
            return

    # Verify
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=10
        )
        logger.info(f"  → Video re-composed: {video_path} ({result.stdout.strip()})")
    except Exception:
        pass

    logger.info("Re-compose complete!")


def cmd_test():
    """Test panel generation only (no CCTV fetch, no publish)."""
    logger.info("Running test mode...")
    ensure_dirs()

    from src.news_extractor import _get_sample_news
    news_items = _get_sample_news()
    news_date = get_today_date()

    logger.info(f"Test news date: {news_date}")
    for item in news_items:
        logger.info(f"  [{item['domain']}] {item['summary']}")

    # Generate assets
    date_str = datetime.now().strftime('%Y%m%d')
    output_dir = os.path.join(BASE_DIR, "output", date_str)
    os.makedirs(output_dir, exist_ok=True)

    assets = _generate_assets(news_items, news_date, output_dir)

    logger.info("Test complete!")


def cmd_backfill():
    """Check for videos due for 48h metrics backfill."""
    init_db()
    pending = get_pending_metrics_videos(hours=48)
    if pending:
        logger.info(f"Found {len(pending)} videos pending metrics backfill:")
        for v in pending:
            logger.info(f"  - {v['video_id']}: {v['title']} (published {v['publish_time']})")
    else:
        logger.info("No videos pending metrics backfill.")


def cmd_manual():
    """Manually input news text and run full generation pipeline."""
    import sys as _sys
    is_pipe = not _sys.stdin.isatty()

    if is_pipe:
        raw_text = _sys.stdin.buffer.read().decode("utf-8", errors="replace")
        end_idx = raw_text.find("END")
        if end_idx >= 0:
            raw_text = raw_text[:end_idx]
    else:
        print("=" * 60)
        print("请输入当天新闻联播内容（每条一行，不限制条数）")
        print("格式: 30% 【金融】央行宣布全面降准0.25个百分点")
        print("输入完成后，输入 END 结束")
        print("=" * 60)

        lines = []
        while True:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                break
            if line.strip().upper() == "END":
                break
            if line.strip():
                lines.append(line)
        raw_text = "\n".join(lines)

    raw_text = raw_text.strip()
    if not raw_text:
        logger.error("No input received. Aborting.")
        return

    news_items = parse_manual_news(raw_text)

    if not news_items:
        logger.error("Could not parse any news items. Aborting.")
        return

    logger.info(f"Parsed {len(news_items)} news items:")
    for item in news_items:
        logger.info(f"  [{item['domain']}] {item['time']} {item['ratio']}%: {item['summary']}")

    # Run generation pipeline
    ensure_dirs()
    init_db()

    news_date = get_today_date()
    date_str = datetime.now().strftime('%Y%m%d')
    video_id = f"news_{date_str}_{uuid.uuid4().hex[:6]}"
    output_dir = os.path.join(BASE_DIR, "output", date_str)
    os.makedirs(output_dir, exist_ok=True)

    # Generate all assets
    assets = _generate_assets(news_items, news_date, output_dir)

    # Compose video & finalize
    result = _compose_video_and_finalize(
        panel_frames=assets["panel_frames"],
        heatmap_img=assets["heatmap_img"],
        voice_path=assets["voice_path"],
        output_dir=output_dir,
        news_date=news_date,
        title=assets["title"],
        main_keyword=assets["main_keyword"],
        video_id=video_id,
        is_exploration=assets["is_exploration"],
    )

    if result:
        print(f"\n{'=' * 60}")
        print(f"生成完成！")
        print(f"  标题: {assets['title']}")
        print(f"  视频: {result}")
        print(f"{'=' * 60}")
    else:
        logger.error("Pipeline failed.")


def run_scheduler():
    """Start the daily scheduler."""
    init_db()
    logger.info("Starting daily scheduler...")

    schedule.every().day.at("20:30").do(cmd_daily)
    logger.info("Scheduled: daily pipeline at 20:30")

    logger.info("Scheduler is running. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user.")
    except Exception as e:
        logger.error(f"Scheduler error: {e}")


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    commands = {
        "daily": cmd_daily,
        "recompose": cmd_recompose,
        "test": cmd_test,
        "manual": cmd_manual,
        "backfill": cmd_backfill,
        "schedule": run_scheduler,
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
