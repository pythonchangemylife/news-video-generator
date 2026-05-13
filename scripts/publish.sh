#!/bin/bash
# publish.sh - 快手"情报搜集站"上传脚本
# 支持定时发布: bash scripts/publish.sh [YYYYMMDD] [标题类型]
#
# 标题类型:
#   A - "{日期}《新闻联播》极速播报：{关键词}"
#   B - "信息差：{日期}新闻联播里暗藏的{领域}机会"  (默认)
#   C - "今天联播最该看的3条：{摘要}"
#
# 不带参数则使用当前日期

set -e
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

DATE_STR="${1:-$(date +%Y%m%d)}"
TITLE_TYPE="${2:-B}"
OUTPUT_DIR="$BASE_DIR/output/$DATE_STR"

if [ ! -f "$OUTPUT_DIR/news_video.mp4" ]; then
    echo "❌ 未找到视频文件: $OUTPUT_DIR/news_video.mp4"
    echo "请先生成视频:"
    echo "  python3 run.py manual"
    exit 1
fi

# 日期显示格式
YEAR="${DATE_STR:0:4}"
MONTH="${DATE_STR:4:2}"
DAY="${DATE_STR:6:2}"
DATE_DISPLAY="${MONTH}月${DAY}日"

# 关键词提取（从 info.txt 或新闻内容）
KEYWORD=""

# 构建标题
case $TITLE_TYPE in
    A)
        TITLE="${DATE_DISPLAY}《新闻联播》极速播报"
        ;;
    B)
        TITLE="信息差：${DATE_DISPLAY}新闻联播里暗藏的政策机会"
        ;;
    C)
        TITLE="今天联播最重要的3条：消费复苏、科技出口、中东局势"
        ;;
    *)
        TITLE="${DATE_DISPLAY}《新闻联播》精华速览"
        ;;
esac

# 描述
DESC="📺 ${DATE_DISPLAY}《新闻联播》精华速览

每天3分钟，掌握政策风向
情报搜集站，让你比别人早一步知道

#新闻联播 #资讯热点 #信息差 #商机"

# 缩略图
THUMBNAIL=""
if [ -f "$OUTPUT_DIR/cover.png" ]; then
    THUMBNAIL="$OUTPUT_DIR/cover.png"
fi

echo "=========================================="
echo "  上传视频到快手 - 情报搜集站"
echo "=========================================="
echo "  日期:    $DATE_STR"
echo "  标题:    $TITLE"
echo "  视频:    $OUTPUT_DIR/news_video.mp4"
echo "  封面:    ${THUMBNAIL:-无}"
echo "=========================================="

# 上传
cd /Users/write_tesla/Desktop/video_uploader
PLAYWRIGHT_BROWSERS_PATH=/Users/write_tesla/Library/Caches/ms-playwright \
  .venv/bin/sau kuaishou upload-video \
    --account news_xwlb \
    --file "$BASE_DIR/$OUTPUT_DIR/news_video.mp4" \
    --title "$TITLE" \
    --desc "$DESC" \
    --tags "新闻联播,资讯热点,信息差,商机" \
    ${THUMBNAIL:+--thumbnail "$THUMBNAIL"} \
    --headless

echo ""
echo "✅ 上传流程完成，请在快手管理后台确认发布状态"
