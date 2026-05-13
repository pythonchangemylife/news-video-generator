"""Video composition module - assemble panels + voice + BGM into final video."""

import os
import random

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)


def pick_bgm():
    """从 assets/bgm 目录中随机挑选一首背景音乐。"""
    bgm_dir = os.path.join(BASE_DIR, CONFIG["voice"]["bgm_dir"])
    if not os.path.isdir(bgm_dir):
        return None

    audio_files = [f for f in os.listdir(bgm_dir)
                   if f.lower().endswith(('.mp3', '.wav'))
                   and os.path.isfile(os.path.join(bgm_dir, f))]
    if audio_files:
        chosen = random.choice(audio_files)
        chosen_path = os.path.join(bgm_dir, chosen)
        print(f"[BGM] 随机选中: {chosen}")
        return chosen_path

    ncm_files = [f for f in os.listdir(bgm_dir) if f.lower().endswith('.ncm')]
    if ncm_files:
        try:
            from ncmdump import NeteaseCloudMusicFile

            ncm_path = os.path.join(bgm_dir, random.choice(ncm_files))
            ncm = NeteaseCloudMusicFile(ncm_path)
            ncm.decrypt()

            output_stem = os.path.join(bgm_dir, os.path.splitext(os.path.basename(ncm_path))[0])
            ncm.dump_music(output_stem)

            for ext in ('.mp3', '.flac'):
                out_path = output_stem + ext
                if os.path.exists(out_path):
                    print(f"[BGM] 转换 NCM: {os.path.basename(out_path)}")
                    return out_path
        except Exception as e:
            print(f"[BGM] NCM 转换失败: {e}")

    return None


def generate_voiceover_sync(news_items, output_path):
    """生成配音（同步调用 edge-tts）。"""
    import asyncio
    import edge_tts

    speed = CONFIG["voice"].get("speed", 1.5)
    rate_str = f"+{int((speed - 1) * 100)}%" if speed >= 1 else f"-{int((1 - speed) * 100)}%"

    parts = []
    for item in news_items:
        domain = item.get("domain", "")
        summary = item.get("summary", "")
        parts.append(f"「{domain}」{summary}")

    text = "。".join(parts)
    if not text.endswith("。"):
        text += "。"

    async def _run():
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural", rate=rate_str)
        await communicate.save(output_path)

    asyncio.run(_run())

    audio_len = os.path.getsize(output_path) / (16000 * 2)
    print(f"[sync] 配音{audio_len:.1f}s, 帧数{len(news_items)}, "
          f"每帧{audio_len / max(len(news_items), 1):.2f}s, "
          f"总长{max(audio_len, len(news_items) * 4):.1f}s")


def compose_video(panel_frames, heatmap_img, voice_path, bgm_path, output_path):
    """将渐进式面板帧 + 热力图 + 配音 + BGM 合成最终视频。"""
    from moviepy import (
        ImageClip, AudioFileClip,
        CompositeAudioClip, concatenate_videoclips
    )

    heatmap_duration = 2.0
    voice_duration = 0
    if voice_path and os.path.exists(voice_path):
        voice_clip = AudioFileClip(voice_path)
        voice_duration = voice_clip.duration
        voice_clip.close()
        print(f"[sync] 配音实际时长: {voice_duration:.2f}s")

    if voice_duration <= 0:
        panel_duration = 0.5
    else:
        panel_total = max(voice_duration - heatmap_duration, 1.0)
        panel_duration = panel_total / max(len(panel_frames), 1)
        panel_duration = max(0.2, panel_duration)

    print(f"[sync] 面板{len(panel_frames)}帧, 每帧{panel_duration:.2f}s, "
          f"配音{voice_duration:.1f}s")

    panels = [ImageClip(np.array(f)).with_duration(panel_duration) for f in panel_frames]
    panel_sequence = concatenate_videoclips(panels, method="compose")

    heatmap_clip = ImageClip(np.array(heatmap_img)).with_duration(heatmap_duration)

    total_video_duration = panel_sequence.duration + heatmap_clip.duration
    final_clip = concatenate_videoclips([panel_sequence, heatmap_clip], method="compose")

    audio_clips = []
    if voice_path and os.path.exists(voice_path):
        audio_clips.append(AudioFileClip(voice_path))
    if bgm_path and os.path.exists(bgm_path):
        bgm_vol = CONFIG["voice"].get("bgm_volume", 0.3)
        bgm_clip = AudioFileClip(bgm_path).with_duration(total_video_duration).with_volume_scaled(bgm_vol)
        audio_clips.append(bgm_clip)

    if audio_clips:
        final_audio = audio_clips[0] if len(audio_clips) == 1 else CompositeAudioClip(audio_clips)
        final_clip = final_clip.with_audio(final_audio)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24,
                               preset="medium", threads=2, logger=None)
    final_clip.close()
    return output_path


import numpy as np
