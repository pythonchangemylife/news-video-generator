"""Video download utilities - stub for use when download_videos=False."""
import os

def download_video(video_url, save_path, max_retries=3):
    """Stub - returns False since we use download_videos=False in daily pipeline."""
    print(f"[download_utils] download_video is stubbed (not needed for text-only crawl)")
    return False
