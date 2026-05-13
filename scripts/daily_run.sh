#!/bin/bash
# daily_run.sh - 快手"情报搜集站"日常运行脚本
# 使用方法: bash scripts/daily_run.sh [YYYYMMDD]
#
# 流程:
#   1. 尝试 crawler 爬取央视新闻 (如果 Playwright 可用)
#   2. 如果爬虫失败，需要手动提供新闻
#   3. 生成视频
#
# 注意: 上传需要手动执行 scripts/publish.sh

set -e
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

DATE_ARG="${1:-}"
PYTHON="$BASE_DIR/venv/bin/python3"

echo "=========================================="
echo "  情报搜集站 - 每日新闻视频生成"
echo "  日期: $(date '+%Y-%m-%d %H:%M')"
echo "=========================================="

# 先尝试爬虫
echo ""
echo "[Step 1] 尝试 Playwright 爬虫..."
PLAYWRIGHT_BROWSERS_PATH=/Users/write_tesla/Library/Caches/ms-playwright \
  $PYTHON run.py daily $DATE_ARG 2>&1

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ 爬虫+生成成功！"
    echo "请执行: bash scripts/publish.sh 来上传视频"
else
    echo ""
    echo "⚠️  爬虫模式失败 (exit=$EXIT_CODE)"
    echo "请使用手动模式:"
    echo "  PLAYWRIGHT_BROWSERS_PATH=... $PYTHON run.py manual"
    echo "  然后输入新闻内容，以 END 结束"
fi
