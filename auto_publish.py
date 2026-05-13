#!/usr/bin/env python3
"""全自动新闻视频流水线：爬虫 → 生成 → 上传快手

用法：
    python auto_publish.py              # 爬取当天新闻 → 生成 → 上传
    python auto_publish.py YYYYMMDD     # 指定日期

环境要求：DeepSeek API Key 配置在 .env 中
"""

import os
import sys
import io
import json
import re
import subprocess
import logging
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from run import run_daily_pipeline, _extract_ymd_from_json_or_date, get_today_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "logs/auto_publish.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("auto_publish")


SAU_CLI = "/Users/write_tesla/Desktop/video_uploader/.venv/bin/python"
SAU_SCRIPT = "/Users/write_tesla/Desktop/video_uploader/sau_cli.py"
KUAISHOU_ACCOUNT = "kuaishou_news_xwlb"
TAGS = "新闻联播,资讯热点,信息差"
VENV_PYTHON = "/Users/write_tesla/.openclaw/workspace/kuaishou-ops/news-video-generator/venv/bin/python3"


def get_today_ymd():
    return datetime.now().strftime("%Y%m%d")


def build_title(news_items):
    """从新闻列表中提取最佳标题。"""
    domains = [item.get("domain", "") for item in news_items]
    domain_tags = [d for d in domains if d]

    # 找占比最高的新闻领域
    sorted_items = sorted(news_items, key=lambda x: x.get("ratio", 0), reverse=True)
    top_domain = sorted_items[0].get("domain", "") if sorted_items else ""
    top_summary = sorted_items[0].get("summary", "") if sorted_items else ""

    # 提取关键词
    keywords = []
    for kw in ["新能源", "AI", "智能", "文旅", "消费", "科技", "经济", "能源", "半导体",
                "芯片", "外贸", "金融", "国债", "基金", "油价", "地产"]:
        for item in news_items[:3]:
            if kw in item.get("summary", ""):
                keywords.append(kw)
                break

    top_keyword = keywords[0] if keywords else top_domain

    # 优先用有信息量的标题格式
    if keywords:
        return f"{top_keyword}大爆发！{get_today_ymd()[:4]}年{get_today_ymd()[4:6]}月{get_today_ymd()[6:8]}日新闻联播极速播报"

    return f"【{top_domain}】{get_today_ymd()[:4]}年{get_today_ymd()[4:6]}月{get_today_ymd()[6:8]}日新闻联播精华速览"


def build_desc(news_items):
    """构建描述文本（摘要每一条 + 标签）。"""
    lines = [f"📺 {get_today_ymd()[:4]}年{get_today_ymd()[4:6]}月{get_today_ymd()[6:8]}日《新闻联播》{len(news_items)}条精华速览\n"]

    for item in news_items:
        summary = item.get("summary", "")
        domain = item.get("domain", "")
        line = f"• {summary}"
        if line not in lines:
            lines.append(line)

    lines.append("\n点赞关注，每天3分钟看懂联播👇")
    return "\n".join(lines)


def upload_to_kuaishou(video_path, title, desc, cover_path=None):
    """调用 sau_cli 上传视频到快手。

    注意：sau_cli 可能在发布后因为导航超时返回非0退出码，
    所以不依赖退出码，而是从 stdout 搜索成功标志。
    """
    if not os.path.exists(video_path):
        logger.error(f"视频文件不存在: {video_path}")
        return False

    logger.info(f"📤 开始上传视频: {title}")

    cmd = [
        SAU_CLI, SAU_SCRIPT, "kuaishou", "upload-video",
        "--account", KUAISHOU_ACCOUNT,
        "--file", video_path,
        "--title", title,
        "--desc", desc,
        "--tags", TAGS,
    ]

    # 封面容易卡快手发布流程，暂时不上传封面
    # if cover_path and os.path.exists(cover_path):
    #     cmd.extend(["--thumbnail", cover_path])
    # else:
    #     cover_path = None
    #     logger.info("  无封面，跳过封面设置")
    pass

    logger.info(f"  → 命令: {' '.join(cmd[:10])}...")

    # 增加长超时（600秒=10分钟），避免 sau_cli 跑 90~100 秒时被外层截断
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                cwd=os.path.dirname(SAU_SCRIPT), timeout=600)
    except subprocess.TimeoutExpired as e:
        # 超时了但可能已经发布成功，尝试从已有的 stdout 判断
        partial_stdout = e.stdout or ""
        logger.warning(f"  ⚠️ subprocess 超时（600s），检查部分 stdout 是否有成功标志")
        success_markers = ["小人开心收工", "发布成功", "视频已经传完啦"]
        for marker in success_markers:
            if marker in partial_stdout:
                logger.info(f"  ✅ 超时但检测到发布成功标志: {marker}")
                return True
        logger.error(f"  ❌ 超时且未检测到成功标志")
        return False
    
    # 输出日志到控制台
    for line in result.stdout.strip().split("\n"):
        logger.info(f"  [sau] {line}")
    if result.stderr and result.stderr.strip():
        for line in result.stderr.strip().split("\n"):
            logger.warning(f"  [sau:err] {line}")

    # 判断标准：搜索 stdout 中是否有发布成功标志
    # 排优先级：小人开心收工 > 视频已经传完啦 > 发布成功（避免"小人发布超时"误认为成功）
    success_markers = ["小人开心收工", "视频已经传完啦", "发布成功"]
    for marker in success_markers:
        if marker in result.stdout:
            logger.info(f"  ✅ 检测到发布成功标志: {marker}")
            return True

    logger.warning(f"  未检测到发布成功标志 (退出码={result.returncode})")

    # 即使未检测到发布标志，如果退出码为0也视为成功（sau_cli 偶发的导航超时但不影响实际发布）
    if result.returncode == 0:
        logger.info(f"  ⚠️ 退出码为0但未检测到明确标志，视为成功")
        return True

    return False


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else None
    if target_date:
        target_date = target_date.replace("-", "").replace("/", "")
        if len(target_date) != 8 or not target_date.isdigit():
            logger.error(f"日期格式无效: {target_date}")
            sys.exit(1)
    else:
        target_date = get_today_ymd()

    logger.info("=" * 50)
    logger.info(f"🚀 全自动视频流水线启动")
    logger.info(f"📅 目标日期: {target_date}")
    logger.info("=" * 50)

    # 设置 stdout/stderr 编码
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    # Step 1: 爬取（使用快速爬虫）
    logger.info("🕷️ Step 1/4: 爬取新闻联播（快速模式）...")
    from crawler_fast import run as fast_crawl_run
    try:
        # run() 是同步函数，直接调用
        success = fast_crawl_run(target_date=target_date)
        if not success:
            logger.error("❌ 爬虫失败")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 爬虫异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 确认爬取到了数据
    dic_path = os.path.join(BASE_DIR, "dic_all_video.json")
    if not os.path.exists(dic_path):
        logger.error("❌ 爬取后未找到 dic_all_video.json")
        sys.exit(1)
    with open(dic_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    logger.info(f"  ✅ 爬取完成: {len(raw_data)} 条新闻")

    # Step 2: 生成视频
    logger.info("🎬 Step 2/4: 生成新闻视频...")
    video_path = run_daily_pipeline()
    if not video_path or not os.path.exists(video_path):
        logger.error("❌ 视频生成失败")
        sys.exit(1)

    logger.info(f"  ✅ 视频生成完成: {video_path}")

    # Step 3: 构建标题和描述
    logger.info("📝 Step 3/4: 构建标题和描述...")
    # 从 dic_all_video.json 获取新闻日期
    news_date = get_today_date()

    # 重新读入 news_items（run_daily_pipeline 已经处理完，但没返回）
    # 从 output 目录的 info.txt 获取信息
    ymd = _extract_ymd_from_json_or_date(news_date)
    output_dir = os.path.join(BASE_DIR, "output", ymd)

    # 取 cover
    cover_path = os.path.join(output_dir, "cover.png")
    if not os.path.exists(cover_path):
        cover_path = None

    # 构建标题和描述
    # 读取最后的日志获取新闻条目
    # 最优方案：从 run_daily_pipeline 内部获取 news_items
    # 但由于 run_daily_pipeline 不返回，我们直接从 info.txt 或后面有

    # 通过解析 run_daily_pipeline 内部已有的 info.txt 来获取内容
    info_path = os.path.join(output_dir, "info.txt")
    title = ""
    if os.path.exists(info_path):
        with open(info_path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
            if lines:
                title = lines[0]

    # 如果没有合适的 title，用通用格式
    if not title or title == f"{ymd}《新闻联播》极速播报版":
        title = f"新能源大爆发！{ymd[:4]}年{ymd[4:6]}月{ymd[6:8]}日新闻联播极速播报"

    # 构建描述 - 从日志解析
    desc_parts = [f"📺 {ymd[:4]}年{ymd[4:6]}月{ymd[6:8]}日《新闻联播》精华速览\n"]
    # 从 run_daily_pipeline 的日志获取 news_items 的摘要
    # 通过 log 文件读取
    log_path = os.path.join(BASE_DIR, "logs/app.log")
    if os.path.exists(log_path):
        summaries = []
        with open(log_path, "r", encoding="utf-8") as f:
            logs = f.readlines()
        for line in logs:
            m = re.search(r'\[(\S+)\]\s+\S+\s+\d+%:\s+(.+)', line)
            if m:
                s = m.group(2).strip()
                if s not in summaries:
                    summaries.append(s)
        if summaries:
            desc_parts = [f"📺 {ymd[:4]}年{ymd[4:6]}月{ymd[6:8]}日《新闻联播》{len(summaries)}条精华速览\n"]
            for s in summaries:
                desc_parts.append(f"• {s}")

    desc_parts.append("\n点赞关注，每天3分钟看懂联播👇")
    desc = "\n".join(desc_parts)

    logger.info(f"  标题: {title}")
    logger.info(f"  描述: {len(desc)} 字符")

    # Step 4: 上传
    logger.info("📤 Step 4/4: 上传到快手...")
    success = upload_to_kuaishou(video_path, title, desc, cover_path)

    if success:
        logger.info("=" * 50)
        logger.info("✅ 全流程完成！视频已发布到快手「情报搜集站」")
        logger.info(f"  标题: {title}")
        logger.info(f"  视频: {video_path}")
        logger.info("=" * 50)

        # 清理 dic_all_video.json
        if os.path.exists(dic_path):
            os.remove(dic_path)
    else:
        logger.error("❌ 上传失败，视频已生成但未发布")
        logger.info(f"  视频在: {video_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
