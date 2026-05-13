#!/usr/bin/env python3
"""上传步骤"""
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SAU_CLI = '/Users/write_tesla/Desktop/video_uploader/.venv/bin/python'
SAU_SCRIPT = '/Users/write_tesla/Desktop/video_uploader/sau_cli.py'
KUAISHOU_ACCOUNT = 'kuaishou_news_xwlb'

video_path = os.path.join(BASE_DIR, 'output/20260508/news_video.mp4')

date_str = '20260508'
title = f'机器人+航天+消费齐爆发！{date_str[:4]}年{date_str[4:6]}月{date_str[6:8]}日新闻联播极速播报'
desc = f'📺 {date_str[:4]}年{date_str[4:6]}月{date_str[6:8]}日《新闻联播》11条精华速览\n'
desc += '• 粤港澳大湾区加快打造高质量发展动力源，国内首条万台级人形机器人生产线启用\n'
desc += '• 我国营商环境持续改善，市场准入负面清单事项压减约14%，民营企业中标占比76.2%\n'
desc += '• 各地培育消费新场景新业态，南京首店60个，淮南商业综合体销售额同比增42%\n'
desc += '• 天舟十号船箭组合体转运至发射区，计划上行物资总重约6.2吨\n'
desc += '• 黑龙江旱田作物播种超8200万亩，四川推广油菜分段式收割模式\n'
desc += '• 一季度末科技型中小企业贷款余额4.03万亿元，同比增长20.9%\n'
desc += '• 《人工智能终端智能化分级》系列国家标准发布，涉及移动终端等多种产品\n'
desc += '• 《国内贸易交易指引（试行）》发布实施，聚焦国内贸易全流程\n'
desc += '• 粮农组织警告中东紧张致化肥短缺，将导致2026下半年至2027年作物减产\n'
desc += '• 美法院裁定美政府10%全球关税政策违法，预计将提出上诉\n'
desc += '• 全球多家航司因航空燃料价格飙升，夏季削减超7.5万个航班\n'
desc += '\n点赞关注，每天3分钟看懂联播👇'

TAGS = '新闻联播,资讯热点,信息差,商机,新能源,假期消费,科技,经济'

print(f'视频: {video_path}')
print(f'标题: {title}')
print(f'描述: {len(desc)}字符')

cmd = [
    SAU_CLI, SAU_SCRIPT, 'kuaishou', 'upload-video',
    '--account', KUAISHOU_ACCOUNT,
    '--file', video_path,
    '--title', title,
    '--desc', desc,
    '--tags', TAGS,
]

print(f'\n执行上传命令...')
result = subprocess.run(cmd, capture_output=True, text=True,
                       cwd=os.path.dirname(SAU_SCRIPT), timeout=300)

for line in result.stdout.strip().split('\n'):
    print(f'  [sau] {line}')
if result.stderr and result.stderr.strip():
    for line in result.stderr.strip().split('\n'):
        print(f'  [sau:err] {line}')

success_markers = ['小人开心收工', '发布成功', '视频已经传完啦']
for marker in success_markers:
    if marker in result.stdout:
        print(f'\n✅ 检测到发布成功标志: {marker}')
        sys.exit(0)

print(f'\n⚠️ 未检测到发布成功标志 (退出码={result.returncode})')
sys.exit(1)
