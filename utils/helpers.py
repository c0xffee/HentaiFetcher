#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher Helpers
=====================
純工具函式（無外部依賴）
"""

import re
import time
import shutil
from pathlib import Path
from datetime import datetime
from typing import List

from core.config import logger, PROGRESS_BAR_WIDTH


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    清理檔案名稱，移除不合法字元
    
    Args:
        name: 原始名稱
        max_length: 最大長度限制（預設 200，保留完整標題）
    
    Returns:
        清理後的安全檔案名稱
    """
    # 移除或替換不合法的檔案名稱字元
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, '_', name)
    
    # 移除前後空白和點
    sanitized = sanitized.strip(' .')
    
    # 只在超過系統限制時才截斷（Linux 檔名上限 255）
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip(' .')
    
    # 如果結果為空，使用預設名稱
    if not sanitized:
        sanitized = f"download_{int(time.time())}"
    
    return sanitized


def generate_eagle_id() -> str:
    """
    生成 Eagle 相容的唯一 ID (基於時間戳)
    
    Returns:
        唯一識別碼字串
    """
    return f"L{int(datetime.now().timestamp() * 1000)}"


def natural_sort_key(s: str):
    """
    自然排序鍵函數 - 讓數字按數值大小排序
    例如: 1.jpg, 2.jpg, 10.jpg 而不是 1.jpg, 10.jpg, 2.jpg
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def create_progress_bar(current: int, total: int, width: int = PROGRESS_BAR_WIDTH) -> str:
    """
    創建 emoji 進度條
    
    Args:
        current: 目前完成數量
        total: 總數量
        width: 進度條寬度（格數）
    
    Returns:
        進度條字串，例如：🟩🟩🟩🟩🟩⬜⬜⬜⬜⬜ 50%
    """
    if total <= 0:
        return "⬜" * width + " 0%"
    
    percentage = min(current / total, 1.0)
    filled = int(percentage * width)
    empty = width - filled
    
    bar = "🟩" * filled + "⬜" * empty
    percent_text = f"{int(percentage * 100)}%"
    
    return f"{bar} {percent_text}"


def format_comment_time(timestamp: int) -> str:
    """格式化評論時間為相對時間"""
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt
    
    if diff.days > 30:
        months = diff.days // 30
        weeks = (diff.days % 30) // 7
        if weeks > 0:
            return f"{months} 個月, {weeks} 週前"
        return f"{months} 個月前"
    elif diff.days > 7:
        weeks = diff.days // 7
        return f"{weeks} 週前"
    elif diff.days > 0:
        return f"{diff.days} 天前"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} 小時前"
    else:
        return f"{diff.seconds // 60} 分鐘前"


def format_comments_for_annotation(comments: list, max_comments: int = 5) -> str:
    """
    格式化評論用於 annotation
    
    Args:
        comments: 評論列表
        max_comments: 最大顯示評論數
    
    Returns:
        格式化的評論字串
    """
    if not comments:
        return ""
    
    lines = ["\n💬 用戶評論:"]
    
    for i, comment in enumerate(comments[:max_comments]):
        username = comment.get('poster', {}).get('username', '匿名')
        body = comment.get('body', '')
        post_date = comment.get('post_date', 0)
        time_str = format_comment_time(post_date) if post_date else ''
        
        lines.append(f"  [{username}] ({time_str})")
        lines.append(f"  {body}")
        if i < len(comments[:max_comments]) - 1:
            lines.append("")
    
    if len(comments) > max_comments:
        lines.append(f"  ... 還有 {len(comments) - max_comments} 則評論")
    
    return "\n".join(lines)


def find_images(directory: Path) -> List[Path]:
    """
    搜尋目錄下的所有圖片檔案
    
    Args:
        directory: 搜尋目錄
    
    Returns:
        圖片檔案路徑列表（已排序）
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
    images = []
    
    for file in directory.rglob('*'):
        # 排除 .part 檔案（未完成的下載）
        if file.suffix.lower() in image_extensions and not file.name.endswith('.part'):
            images.append(file)
    
    # 按檔名自然排序
    def _natural_sort_key(path: Path):
        # 提取數字進行自然排序
        numbers = re.findall(r'\d+', path.stem)
        return [int(n) for n in numbers] if numbers else [path.stem]
    
    images.sort(key=_natural_sort_key)
    return images


def get_first_image_as_cover(folder_path: Path) -> bool:
    """
    使用資料夾內的第一張圖片作為封面
    
    Args:
        folder_path: 資料夾路徑
    
    Returns:
        是否成功
    """
    try:
        # 支援的圖片格式
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        
        # 找到所有圖片（排除已有的 cover 開頭檔案）
        images = []
        for file in folder_path.iterdir():
            if file.is_file() and file.suffix.lower() in image_extensions:
                # 排除封面檔案
                if not file.stem.lower().startswith('cover'):
                    images.append(file)
        
        if not images:
            logger.warning(f"資料夾內沒有可用的圖片: {folder_path}")
            return False
        
        # 按檔名自然排序，取第一張
        images.sort(key=lambda x: natural_sort_key(x.name))
        first_image = images[0]
        
        # 複製為封面
        cover_ext = first_image.suffix.lower()
        cover_path = folder_path / f"cover{cover_ext}"
        
        shutil.copy2(first_image, cover_path)
        logger.info(f"已使用第一張圖片作為封面: {first_image.name} -> cover{cover_ext}")
        return True
        
    except Exception as e:
        logger.error(f"使用第一張圖片作為封面失敗: {e}")
        return False
