#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher - Discord Bot 自動化漫畫下載器
==============================================
版本: 3.0.0 - 斜線指令版本
功能：
1. Discord Bot 使用斜線指令 (/dl, /search, /read 等)
2. 使用 gallery-dl 下載圖片與 metadata
3. 使用 Pillow 轉換為等寬 PDF
4. 生成 Eagle 相容的 metadata.json
5. 自動清理原始圖片檔案
6. 整合 Eagle Library 查詢
"""

# 版本號 - 用來確認容器是否更新
VERSION = "3.3.6"

print(f"[STARTUP] HentaiFetcher 版本 {VERSION} 正在載入...", flush=True)

import os
import sys
import json
import time
import shutil
import asyncio
import logging
import subprocess
import threading
import re
import requests
from queue import Queue, Empty
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import quote

import discord
from discord.ext import commands
from discord import app_commands

# 載入 .env 檔案（本地測試用）
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[STARTUP] 已載入 .env 檔案", flush=True)
except ImportError:
    pass  # Docker 環境不需要 dotenv

print(f"[STARTUP] 模組載入完成", flush=True)

# ==================== 設定區塊 ====================

# 判斷運行環境（Docker 或本地）
import platform
IS_DOCKER = platform.system() == 'Linux' and os.path.exists('/app')

if IS_DOCKER:
    # Docker 環境 - 使用容器內路徑
    BASE_DIR = Path('/app')
    print("[STARTUP] 運行環境: Docker", flush=True)
else:
    # 本地測試環境 - 使用專案資料夾
    BASE_DIR = Path(__file__).parent.resolve()
    print(f"[STARTUP] 運行環境: 本地 ({BASE_DIR})", flush=True)

# 統一使用相同的子資料夾
CONFIG_DIR = BASE_DIR / 'config'
DOWNLOAD_DIR = BASE_DIR / 'downloads'
TEMP_DIR = BASE_DIR / 'temp'

# 確保目錄存在
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# 日誌設定
log_file = CONFIG_DIR / 'bot.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding='utf-8')
    ]
)
logger = logging.getLogger('HentaiFetcher')

# 下載佇列 - 結構: (url, channel_id, status_message_id, force_mode, batch_id)
download_queue: Queue = Queue()

# 取消下載追蹤器 - 用於標記需要取消的下載任務
# 結構: {gallery_id: threading.Event}  - Event 被 set 時表示任務應該被取消
cancel_events: Dict[str, threading.Event] = {}
cancel_lock = threading.Lock()

def request_cancel(gallery_id: str) -> bool:
    """請求取消下載"""
    with cancel_lock:
        if gallery_id in cancel_events:
            cancel_events[gallery_id].set()
            return True
        return False

def register_cancel_event(gallery_id: str) -> threading.Event:
    """註冊取消事件"""
    with cancel_lock:
        event = threading.Event()
        cancel_events[gallery_id] = event
        return event

def unregister_cancel_event(gallery_id: str):
    """取消註冊取消事件"""
    with cancel_lock:
        cancel_events.pop(gallery_id, None)

def is_cancelled(gallery_id: str) -> bool:
    """檢查是否已被取消"""
    with cancel_lock:
        event = cancel_events.get(gallery_id)
        return event.is_set() if event else False

# 批次下載追蹤器 - 用於統計多檔案下載結果
# 結構: {batch_id: {'total': int, 'success': int, 'failed': int, 'channel_id': int, 'gallery_ids': List[str]}}
batch_tracker: Dict[str, Dict[str, Any]] = {}
batch_lock = threading.Lock()

def generate_batch_id() -> str:
    """生成批次 ID"""
    return f"B{int(datetime.now().timestamp() * 1000)}"

def init_batch(batch_id: str, total: int, channel_id: int, gallery_ids: List[str]):
    """初始化批次追蹤"""
    with batch_lock:
        batch_tracker[batch_id] = {
            'total': total,
            'success': 0,
            'failed': 0,
            'channel_id': channel_id,
            'gallery_ids': gallery_ids,
            'completed_ids': [],
            'failed_ids': []
        }

def update_batch(batch_id: str, success: bool, gallery_id: str = None) -> Optional[Dict[str, Any]]:
    """
    更新批次狀態，如果完成則返回統計結果
    
    Returns:
        如果批次完成，返回統計資訊；否則返回 None
    """
    with batch_lock:
        if batch_id not in batch_tracker:
            return None
        
        batch = batch_tracker[batch_id]
        if success:
            batch['success'] += 1
            if gallery_id:
                batch['completed_ids'].append(gallery_id)
        else:
            batch['failed'] += 1
            if gallery_id:
                batch['failed_ids'].append(gallery_id)
        
        # 檢查是否完成
        if batch['success'] + batch['failed'] >= batch['total']:
            result = batch.copy()
            del batch_tracker[batch_id]
            return result
        
        return None

# 進度條設定
PROGRESS_UPDATE_INTERVAL = 3  # 每 3 秒更新一次進度
SECONDS_PER_PAGE = 3.6  # 預估每頁下載時間（實測平均值）
PROGRESS_BAR_WIDTH = 15  # 進度條寬度（格數）

# PDF Web 存取設定
PDF_WEB_BASE_URL = "http://192.168.0.32:8888"  # Web Station 基礎 URL


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


# 訊息去重（避免重複處理同一訊息）
processed_messages: set = set()

# 專用頻道設定 - 在這些頻道中不需要 !dl 前綴
# 可設定頻道名稱或頻道 ID（設定名稱更方便）
DEDICATED_CHANNEL_NAMES = ['hentaifetcher', 'hentai-fetcher', 'nhentai']  # 頻道名稱
DEDICATED_CHANNEL_IDS = []  # 或直接設定頻道 ID
MAX_PROCESSED_MESSAGES = 1000  # 最多保留 1000 筆記錄

def is_message_processed(message_id: int) -> bool:
    """檢查訊息是否已處理過"""
    global processed_messages
    if message_id in processed_messages:
        return True
    
    # 清理過舊的記錄
    if len(processed_messages) >= MAX_PROCESSED_MESSAGES:
        # 清除一半的記錄
        processed_messages = set(list(processed_messages)[MAX_PROCESSED_MESSAGES // 2:])
    
    processed_messages.add(message_id)
    return False

# ==================== 工具函式 ====================

def parse_input_to_urls(input_text: str) -> List[str]:
    """
    解析使用者輸入，支援多種格式：
    - 完整網址: https://nhentai.net/g/123456/
    - 純數字: 123456
    - 多個輸入（空白、逗號、換行分隔）
    - 混合輸入: 421633 https://nhentai.net/g/607769/ 613358
    
    Args:
        input_text: 使用者輸入的文字
    
    Returns:
        解析後的完整 URL 列表
    """
    urls = []
    
    # 標準化換行符號（處理 Windows/Mac/Linux 不同的換行）
    normalized_text = input_text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Debug 日誌
    logger.debug(f"原始輸入: {repr(input_text)}")
    logger.debug(f"標準化後: {repr(normalized_text)}")
    
    # 按行分割處理
    lines = normalized_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 每行可能有多個項目（空白或逗號分隔）
        parts = re.split(r'[\s,;]+', line)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 如果是完整 URL
            if part.startswith(('http://', 'https://')):
                # 清理 URL 結尾可能的標點符號
                url = part.rstrip('.,;')
                urls.append(url)
            # 如果是純數字
            elif part.isdigit():
                urls.append(f"https://nhentai.net/g/{part}/")
            # 嘗試提取數字（例如: g/123456 或 #123456）
            else:
                match = re.search(r'(\d{4,7})', part)
                if match:
                    urls.append(f"https://nhentai.net/g/{match.group(1)}/")
    
    # 去除重複並保持順序
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    logger.info(f"解析到 {len(unique_urls)} 個 URL")
    return unique_urls


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


# 快速 reindex 標記 - 用於避免頻繁重複索引
_last_reindex_time: float = 0
REINDEX_COOLDOWN = 60  # 60 秒內不重複 reindex

def quick_reindex() -> int:
    """
    快速重建索引 (有冷卻時間限制)
    
    Returns:
        新增項目數，如果跳過則返回 -1
    """
    global _last_reindex_time
    
    current_time = time.time()
    if current_time - _last_reindex_time < REINDEX_COOLDOWN:
        logger.debug(f"跳過 reindex (冷卻中)")
        return -1
    
    try:
        from eagle_library import EagleLibrary
        eagle = EagleLibrary()
        added = eagle.rebuild_index()
        _last_reindex_time = time.time()
        logger.info(f"快速 reindex 完成，新增 {added} 項")
        return added
    except Exception as e:
        logger.warning(f"快速 reindex 失敗: {e}")
        return 0


def check_already_downloaded(gallery_id: str, do_reindex: bool = False) -> tuple[bool, Optional[dict]]:
    """
    檢查 gallery 是否已經下載過 (存在於 Eagle Library)
    
    Args:
        gallery_id: nhentai Gallery ID
        do_reindex: 是否先執行快速 reindex
    
    Returns:
        (已存在, 結果資訊) - 如果已存在，結果包含 web_url, title 等
    """
    try:
        # 可選：先執行快速 reindex
        if do_reindex:
            quick_reindex()
        
        from eagle_library import EagleLibrary
        eagle = EagleLibrary()
        result = eagle.find_by_nhentai_id(gallery_id)
        if result:
            return True, result
        return False, None
    except Exception as e:
        logger.warning(f"檢查重複下載時發生錯誤: {e}")
        return False, None


def verify_nhentai_url(gallery_id: str) -> tuple[bool, str]:
    """
    驗證 nhentai gallery 是否存在且可訪問
    
    Args:
        gallery_id: Gallery ID
    
    Returns:
        (是否有效, 標題或錯誤訊息)
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            title = data.get('title', {}).get('english', '') or data.get('title', {}).get('japanese', '')
            return True, title[:50] + '...' if len(title) > 50 else title
        elif response.status_code == 404:
            return False, "Gallery 不存在"
        else:
            return False, f"HTTP {response.status_code}"
    except requests.Timeout:
        return False, "連線逾時"
    except Exception as e:
        return False, str(e)


def get_nhentai_page_count(gallery_id: str) -> tuple[int, str, str]:
    """
    從 nhentai API 獲取頁數、標題和 media_id
    
    Args:
        gallery_id: Gallery ID
    
    Returns:
        (頁數, 標題, media_id) - 失敗時頁數為 0
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            pages = data.get('num_pages', 0)
            title = data.get('title', {}).get('japanese', '') or data.get('title', {}).get('english', '')
            media_id = str(data.get('media_id', ''))
            return pages, title[:40] + '...' if len(title) > 40 else title, media_id
    except:
        pass
    
    return 0, "", ""


def fetch_nhentai_extra_info(gallery_id: str) -> Dict[str, Any]:
    """
    從 nhentai API 獲取額外資訊（收藏數、評論等）
    
    Args:
        gallery_id: Gallery ID
    
    Returns:
        包含 favorites 和 comments 的字典
    """
    result = {
        'favorites': 0,
        'comments': []
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # 獲取收藏數
    try:
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            result['favorites'] = data.get('num_favorites', 0)
            logger.info(f"獲取收藏數: {result['favorites']}")
    except Exception as e:
        logger.warning(f"獲取收藏數失敗: {e}")
    
    # 獲取評論
    try:
        comments_url = f"https://nhentai.net/api/gallery/{gallery_id}/comments"
        response = requests.get(comments_url, headers=headers, timeout=30)
        if response.status_code == 200:
            result['comments'] = response.json()
            logger.info(f"獲取評論數: {len(result['comments'])}")
    except Exception as e:
        logger.warning(f"獲取評論失敗: {e}")
    
    return result


def download_nhentai_cover(gallery_id: str, save_path: Path) -> bool:
    """
    從 nhentai 下載封面圖片
    
    Args:
        gallery_id: Gallery ID
        save_path: 保存路徑（資料夾）
    
    Returns:
        是否成功
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # 獲取 gallery 資訊
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code != 200:
            logger.warning(f"無法獲取 gallery 資訊: {gallery_id}")
            return False
        
        data = response.json()
        media_id = data.get('media_id', '')
        if not media_id:
            logger.warning(f"找不到 media_id: {gallery_id}")
            return False
        
        # 獲取封面格式
        images = data.get('images', {})
        cover = images.get('cover', {})
        cover_type = cover.get('t', 'j')  # j=jpg, p=png, g=gif
        
        ext_map = {'j': 'jpg', 'p': 'png', 'g': 'gif'}
        ext = ext_map.get(cover_type, 'jpg')
        
        # 嘗試多個 URL 格式下載封面
        cover_urls = [
            f"https://t.nhentai.net/galleries/{media_id}/cover.{ext}",
            f"https://t3.nhentai.net/galleries/{media_id}/cover.{ext}",
            f"https://i.nhentai.net/galleries/{media_id}/cover.{ext}",
            f"https://i5.nhentai.net/galleries/{media_id}/cover.{ext}",
        ]
        
        for cover_url in cover_urls:
            try:
                logger.info(f"嘗試下載封面: {cover_url}")
                response = requests.get(cover_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    cover_path = save_path / f"cover.{ext}"
                    with open(cover_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"封面已保存: {cover_path}")
                    return True
            except Exception as e:
                logger.debug(f"嘗試 {cover_url} 失敗: {e}")
                continue
        
        logger.warning(f"所有封面 URL 都失敗")
        return False
            
    except Exception as e:
        logger.error(f"下載封面錯誤: {e}")
        return False


def download_nhentai_first_page(gallery_id: str, save_path: Path) -> bool:
    """
    從 nhentai 下載第一頁圖片作為封面（備用方案）
    
    Args:
        gallery_id: Gallery ID
        save_path: 保存路徑（資料夾）
    
    Returns:
        是否成功
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # 獲取 gallery 資訊
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=headers, timeout=30)
        if response.status_code != 200:
            logger.warning(f"無法獲取 gallery 資訊: {gallery_id}")
            return False
        
        data = response.json()
        media_id = data.get('media_id', '')
        if not media_id:
            logger.warning(f"找不到 media_id: {gallery_id}")
            return False
        
        # 獲取第一頁格式
        images = data.get('images', {})
        pages = images.get('pages', [])
        if not pages:
            logger.warning(f"找不到頁面資訊: {gallery_id}")
            return False
        
        first_page = pages[0]
        page_type = first_page.get('t', 'j')  # j=jpg, p=png, g=gif, w=webp
        
        ext_map = {'j': 'jpg', 'p': 'png', 'g': 'gif', 'w': 'webp'}
        ext = ext_map.get(page_type, 'jpg')
        
        # 嘗試多個 URL 格式下載第一頁
        first_page_urls = [
            f"https://i.nhentai.net/galleries/{media_id}/1.{ext}",
            f"https://i2.nhentai.net/galleries/{media_id}/1.{ext}",
            f"https://i5.nhentai.net/galleries/{media_id}/1.{ext}",
            f"https://i7.nhentai.net/galleries/{media_id}/1.{ext}",
        ]
        
        for page_url in first_page_urls:
            try:
                logger.info(f"嘗試下載第一頁作為封面: {page_url}")
                response = requests.get(page_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    cover_path = save_path / f"cover.{ext}"
                    with open(cover_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"第一頁已保存為封面: {cover_path}")
                    return True
            except Exception as e:
                logger.debug(f"嘗試 {page_url} 失敗: {e}")
                continue
        
        logger.warning(f"所有第一頁 URL 都失敗")
        return False
            
    except Exception as e:
        logger.error(f"下載第一頁錯誤: {e}")
        return False


def natural_sort_key(s: str):
    """
    自然排序鍵函數 - 讓數字按數值大小排序
    例如: 1.jpg, 2.jpg, 10.jpg 而不是 1.jpg, 10.jpg, 2.jpg
    """
    import re
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


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
        
        import shutil
        shutil.copy2(first_image, cover_path)
        logger.info(f"已使用第一張圖片作為封面: {first_image.name} -> cover{cover_ext}")
        return True
        
    except Exception as e:
        logger.error(f"使用第一張圖片作為封面失敗: {e}")
        return False


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


def parse_gallery_dl_info(info_path: Path) -> Optional[Dict[str, Any]]:
    """
    解析 gallery-dl 生成的 info.json 或 gallery_metadata.json
    
    gallery-dl --dump-json 輸出格式:
    {
        "title": "...",
        "title_en": "...",
        "title_ja": "...",
        "gallery_id": 123456,
        "count": 34,
        "type": "doujinshi",
        "artist": ["name"],
        "group": ["name"],
        "parody": ["name"],
        "characters": [],
        "language": "Chinese",
        "tags": ["tag1", "tag2", ...]
    }
    
    Args:
        info_path: info.json 檔案路徑
    
    Returns:
        解析後的 metadata 字典，失敗則返回 None
    """
    try:
        with open(info_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 初始化結果結構（擴展版）
        result = {
            'title': '',
            'title_japanese': '',  # 日文副標題
            'title_pretty': '',    # 簡短標題
            'tags': [],
            'url': '',
            'gallery_id': '',
            'pages': 0,
            'favorites': 0,
            'category': '',
            'type': '',
            'artist': [],
            'group': [],
            'parody': [],
            'character': [],
            'language': '',
        }
        
        # 處理 gallery-dl 輸出格式
        if isinstance(data, dict):
            # ===== 標題處理 =====
            # gallery-dl 格式: title, title_en, title_ja 都是字串
            if 'title' in data:
                if isinstance(data['title'], dict):
                    # 舊版 nhentai API 格式: {"english": "...", "japanese": "...", "pretty": "..."}
                    result['title'] = (
                        data['title'].get('english') or 
                        data['title'].get('pretty') or 
                        data['title'].get('japanese') or 
                        ''
                    )
                    result['title_japanese'] = data['title'].get('japanese', '')
                    result['title_pretty'] = data['title'].get('pretty', '')
                else:
                    result['title'] = str(data['title'])
            
            # gallery-dl 使用 title_en 和 title_ja
            if 'title_en' in data:
                if not result['title']:
                    result['title'] = data['title_en']
            
            if 'title_ja' in data:
                result['title_japanese'] = data['title_ja']
            
            # ===== Gallery ID =====
            if 'gallery_id' in data:
                result['gallery_id'] = str(data['gallery_id'])
            elif 'id' in data:
                result['gallery_id'] = str(data['id'])
            
            # ===== 頁數 =====
            # gallery-dl 使用 count，nhentai API 使用 num_pages
            if 'count' in data:
                result['pages'] = int(data['count'])
            elif 'num_pages' in data:
                result['pages'] = int(data['num_pages'])
            
            # ===== 收藏數 =====
            if 'num_favorites' in data:
                result['favorites'] = int(data['num_favorites'])
            
            # ===== 類型 (doujinshi, manga, etc.) =====
            if 'type' in data:
                result['type'] = data['type']
                result['category'] = data['type']  # 兼容舊格式
            
            # ===== 作者列表 =====
            if 'artist' in data:
                if isinstance(data['artist'], list):
                    result['artist'] = data['artist']
                    for artist in data['artist']:
                        result['tags'].append(f"artist:{artist}")
                elif isinstance(data['artist'], str):
                    result['artist'] = [data['artist']]
                    result['tags'].append(f"artist:{data['artist']}")
            
            # ===== 社團列表 =====
            if 'group' in data:
                if isinstance(data['group'], list):
                    result['group'] = data['group']
                    for group in data['group']:
                        result['tags'].append(f"group:{group}")
                elif isinstance(data['group'], str):
                    result['group'] = [data['group']]
                    result['tags'].append(f"group:{data['group']}")
            
            # ===== 原作列表 =====
            if 'parody' in data:
                if isinstance(data['parody'], list):
                    result['parody'] = data['parody']
                    for parody in data['parody']:
                        result['tags'].append(f"parody:{parody}")
                elif isinstance(data['parody'], str):
                    result['parody'] = [data['parody']]
                    result['tags'].append(f"parody:{data['parody']}")
            
            # ===== 角色列表 =====
            # gallery-dl 使用 characters (複數)
            if 'characters' in data:
                if isinstance(data['characters'], list):
                    result['character'] = data['characters']
                    for char in data['characters']:
                        result['tags'].append(f"character:{char}")
            elif 'character' in data:
                if isinstance(data['character'], list):
                    result['character'] = data['character']
                    for char in data['character']:
                        result['tags'].append(f"character:{char}")
            
            # ===== 語言 =====
            if 'language' in data:
                result['language'] = data['language']
                result['tags'].append(f"language:{data['language']}")
            
            # ===== 標籤處理 =====
            if 'tags' in data:
                tags = data['tags']
                if isinstance(tags, list):
                    for tag in tags:
                        if isinstance(tag, dict):
                            # 舊版 nhentai API 格式: {type, name}
                            tag_name = tag.get('name', '')
                            tag_type = tag.get('type', '')
                            if tag_name:
                                if tag_type == 'category':
                                    result['category'] = tag_name
                                    result['tags'].append(f"category:{tag_name}")
                                elif tag_type == 'artist':
                                    if tag_name not in result['artist']:
                                        result['artist'].append(tag_name)
                                        result['tags'].append(f"artist:{tag_name}")
                                elif tag_type == 'group':
                                    if tag_name not in result['group']:
                                        result['group'].append(tag_name)
                                        result['tags'].append(f"group:{tag_name}")
                                elif tag_type == 'parody':
                                    if tag_name not in result['parody']:
                                        result['parody'].append(tag_name)
                                        result['tags'].append(f"parody:{tag_name}")
                                elif tag_type == 'character':
                                    if tag_name not in result['character']:
                                        result['character'].append(tag_name)
                                        result['tags'].append(f"character:{tag_name}")
                                elif tag_type == 'language':
                                    result['language'] = tag_name
                                    result['tags'].append(f"language:{tag_name}")
                                elif tag_type in ['tag', '']:
                                    result['tags'].append(tag_name)
                                else:
                                    result['tags'].append(f"{tag_type}:{tag_name}")
                        elif isinstance(tag, str):
                            # gallery-dl 格式: 直接字串陣列
                            result['tags'].append(tag)
                elif isinstance(tags, str):
                    result['tags'] = [t.strip() for t in tags.split(',') if t.strip()]
            
            # ===== 類型標籤 =====
            if result['type']:
                result['tags'].append(f"type:{result['type']}")
            
            # ===== URL 處理 =====
            if 'gallery_url' in data:
                result['url'] = data['gallery_url']
            elif 'url' in data:
                result['url'] = data['url']
            
            # 嘗試從 gallery_id 構建 URL
            if not result['url'] and result['gallery_id']:
                result['url'] = f"https://nhentai.net/g/{result['gallery_id']}/"
        
        # 去除重複標籤
        result['tags'] = list(dict.fromkeys(result['tags']))
        
        logger.info(f"解析到標題: {result['title']}")
        logger.info(f"  日文標題: {result['title_japanese']}")
        logger.info(f"  Gallery ID: {result['gallery_id']}, 頁數: {result['pages']}")
        logger.info(f"  作者: {result['artist']}, 社團: {result['group']}")
        logger.info(f"  類型: {result['type']}, 語言: {result['language']}")
        logger.info(f"  標籤數: {len(result['tags'])}")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析錯誤: {e}")
        return None
    except Exception as e:
        logger.error(f"解析 info.json 時發生錯誤: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def create_eagle_metadata(
    title: str,
    url: str,
    tags: List[str],
    annotation: str = "",
    extra_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    建立 Eagle 相容的 metadata.json 內容
    
    Eagle 標準欄位：
    - id: 唯一識別碼
    - name: 名稱
    - tags: 標籤列表 (Array)
    - url / website: 來源網址
    - annotation: 註釋/備註 (冗長資訊放這裡)
    
    Args:
        title: 漫畫標題
        url: 來源網址
        tags: 標籤列表
        annotation: 基本備註
        extra_info: 額外資訊（副標題、頁數、收藏數等）
    
    Returns:
        Eagle metadata 字典
    """
    # 建立完整的 tags 列表
    all_tags = list(tags)  # 複製原有標籤
    
    # 建立 annotation 內容
    annotation_lines = []
    
    if extra_info:
        # ===== 加入額外標籤 =====
        # 類型標籤
        if extra_info.get('type'):
            type_tag = f"type:{extra_info['type']}"
            if type_tag not in all_tags:
                all_tags.append(type_tag)
        
        # 語言標籤
        if extra_info.get('language'):
            lang_tag = f"language:{extra_info['language']}"
            if lang_tag not in all_tags:
                all_tags.append(lang_tag)
        
        # 作者標籤
        if extra_info.get('artist'):
            for artist in extra_info['artist']:
                artist_tag = f"artist:{artist}"
                if artist_tag not in all_tags:
                    all_tags.append(artist_tag)
        
        # 社團標籤
        if extra_info.get('group'):
            for group in extra_info['group']:
                group_tag = f"group:{group}"
                if group_tag not in all_tags:
                    all_tags.append(group_tag)
        
        # 原作標籤
        if extra_info.get('parody'):
            for parody in extra_info['parody']:
                parody_tag = f"parody:{parody}"
                if parody_tag not in all_tags:
                    all_tags.append(parody_tag)
        
        # 角色標籤
        if extra_info.get('character'):
            for char in extra_info['character']:
                char_tag = f"character:{char}"
                if char_tag not in all_tags:
                    all_tags.append(char_tag)
        
        # ===== 建立 annotation 內容 =====
        # 英文標題（如果主標題是日文，顯示英文標題作為參考）
        if extra_info.get('title_english'):
            annotation_lines.append(f"📖 英文標題: {extra_info['title_english']}")
        
        # 頁數
        if extra_info.get('pages'):
            annotation_lines.append(f"📄 頁數: {extra_info['pages']}")
        
        # 收藏數
        if extra_info.get('favorites') and extra_info['favorites'] > 0:
            annotation_lines.append(f"❤️ 收藏數: {extra_info['favorites']}")
        
        # 類型
        if extra_info.get('type'):
            annotation_lines.append(f"📁 類型: {extra_info['type']}")
        
        # 語言
        if extra_info.get('language'):
            annotation_lines.append(f"🌐 語言: {extra_info['language']}")
        
        # 作者
        if extra_info.get('artist'):
            annotation_lines.append(f"🎨 作者: {', '.join(extra_info['artist'])}")
        
        # 社團
        if extra_info.get('group'):
            annotation_lines.append(f"👥 社團: {', '.join(extra_info['group'])}")
        
        # 原作
        if extra_info.get('parody'):
            annotation_lines.append(f"🎬 原作: {', '.join(extra_info['parody'])}")
        
        # 角色
        if extra_info.get('character') and len(extra_info['character']) > 0:
            annotation_lines.append(f"👤 角色: {', '.join(extra_info['character'])}")
        
        # ID (放在較下面)
        if extra_info.get('gallery_id'):
            annotation_lines.append(f"📔 ID: {extra_info['gallery_id']}")
        
        # 用戶評論
        if extra_info.get('comments'):
            comments_text = format_comments_for_annotation(extra_info['comments'])
            if comments_text:
                annotation_lines.append(comments_text)
    
    # 加入下載時間
    annotation_lines.append(f"\n⏰ 下載時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    annotation_lines.append("📥 Downloaded via HentaiFetcher Bot")
    
    # 如果有額外的基本備註，加在最後
    if annotation and annotation != "Downloaded via HentaiFetcher Bot":
        annotation_lines.append(f"\n{annotation}")
    
    # 去除重複標籤
    all_tags = list(dict.fromkeys(all_tags))
    
    # 建立最終 metadata
    metadata = {
        "id": generate_eagle_id(),
        "name": title,
        "url": url,
        "tags": all_tags,
        "annotation": "\n".join(annotation_lines)
    }
    
    return metadata


def find_info_json(directory: Path) -> Optional[Path]:
    """
    遞迴搜尋 info.json 檔案
    
    Args:
        directory: 搜尋起始目錄
    
    Returns:
        找到的 info.json 路徑，未找到則返回 None
    """
    # 優先搜尋我們自己生成的 metadata 檔案
    our_metadata = directory / "gallery_metadata.json"
    if our_metadata.exists():
        return our_metadata
    
    # 直接在目錄下搜尋
    for json_file in directory.rglob('*.json'):
        if json_file.name == 'info.json' or 'info' in json_file.name.lower():
            return json_file
    
    # 也嘗試搜尋其他可能的 metadata 檔案
    for json_file in directory.rglob('*.json'):
        return json_file  # 返回第一個找到的 JSON
    
    return None


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
    def natural_sort_key(path: Path):
        # 提取數字進行自然排序
        numbers = re.findall(r'\d+', path.stem)
        return [int(n) for n in numbers] if numbers else [path.stem]
    
    images.sort(key=natural_sort_key)
    return images


# ==================== 下載處理類別 ====================

class DownloadProcessor:
    """
    下載處理器：負責執行 gallery-dl、轉換 PDF 並生成 metadata
    """
    
    def __init__(self, url: str, total_pages: int = 0, message_callback=None, cancel_event: threading.Event = None):
        """
        初始化下載處理器
        
        Args:
            url: 要下載的網址
            total_pages: 預期總頁數（用於進度計算）
            message_callback: 狀態更新回調函式
            cancel_event: 取消事件（被 set 時應中止下載）
        """
        self.url = url
        self.total_pages = total_pages
        self.message_callback = message_callback
        self.cancel_event = cancel_event
        self.temp_path: Optional[Path] = None
        self.output_path: Optional[Path] = None
        self.last_error: str = ""
        self.download_complete = False  # 下載是否完成
        self.pdf_progress = 0  # PDF 轉換進度 (0-100)
        self.pdf_converting = False  # 是否正在轉換 PDF
    
    def is_cancelled(self) -> bool:
        """檢查是否已被取消"""
        return self.cancel_event and self.cancel_event.is_set()
        
    def get_downloaded_count(self) -> int:
        """獲取已下載的圖片數量"""
        if not self.temp_path or not self.temp_path.exists():
            return 0
        return len(find_images(self.temp_path))
    
    def get_first_image_path(self) -> Path:
        """獲取第一張已下載圖片的路徑"""
        if not self.temp_path or not self.temp_path.exists():
            return None
        images = find_images(self.temp_path)
        if images:
            # 按檔名排序取第一張
            images.sort(key=lambda x: x.name)
            return images[0]
        return None
        
    async def send_status(self, message: str):
        """發送狀態訊息"""
        logger.info(message)
        if self.message_callback:
            try:
                await self.message_callback(message)
            except Exception as e:
                logger.warning(f"無法發送狀態訊息: {e}")
    
    def download_with_gallery_dl(self) -> bool:
        """
        使用 gallery-dl 下載圖片和 metadata
        
        Returns:
            成功返回 True，失敗返回 False
        """
        try:
            # 建立唯一的暫存目錄（統一使用 TEMP_DIR）
            self.temp_path = TEMP_DIR / f"dl_{int(time.time() * 1000)}"
            self.temp_path.mkdir(parents=True, exist_ok=True)
            
            print(f"[GALLERY-DL] 下載目錄: {self.temp_path}", flush=True)
            
            # 根據環境選擇 gallery-dl 執行方式與參數
            if IS_DOCKER:
                # Docker 環境：兩階段下載
                # 階段 1: 使用 gallery-dl --dump-json 獲取 metadata
                print(f"[GALLERY-DL] 階段1: 獲取 metadata...", flush=True)
                metadata_cmd = [
                    'gallery-dl',
                    '--dump-json',
                    '--user-agent', 'Mozilla/5.0',
                    self.url
                ]
                
                metadata_result = subprocess.run(
                    metadata_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                # 解析並儲存 metadata
                if metadata_result.returncode == 0 and metadata_result.stdout.strip():
                    try:
                        # gallery-dl --dump-json 輸出的是 JSON 陣列
                        metadata_list = json.loads(metadata_result.stdout)
                        if metadata_list and len(metadata_list) > 0:
                            # 取第一個元素的 metadata（通常包含 gallery info）
                            first_item = metadata_list[0]
                            if isinstance(first_item, list) and len(first_item) >= 2:
                                gallery_metadata = first_item[1]  # [url, metadata] 格式
                            else:
                                gallery_metadata = first_item
                            
                            # 儲存 metadata 到暫存目錄
                            metadata_file = self.temp_path / "gallery_metadata.json"
                            with open(metadata_file, 'w', encoding='utf-8') as f:
                                json.dump(gallery_metadata, f, ensure_ascii=False, indent=2)
                            print(f"[GALLERY-DL] Metadata 已儲存: {metadata_file}", flush=True)
                    except json.JSONDecodeError as e:
                        print(f"[GALLERY-DL] Metadata 解析失敗: {e}", flush=True)
                
                # 階段 2: 使用 gallery-dl -g + aria2c 多線程下載圖片
                print(f"[GALLERY-DL] 階段2: 多線程下載圖片...", flush=True)
                cmd = (
                    f'gallery-dl --user-agent "Mozilla/5.0" -g "{self.url}" | '
                    f'aria2c -i - -x 8 -s 8 --user-agent="Mozilla/5.0" -d "{self.temp_path}"'
                )
                
                logger.info(f"執行指令: {cmd}")
                print(f"[GALLERY-DL+ARIA2] 命令: {cmd}", flush=True)
                
                # 使用 shell=True 執行管道命令
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=900
                )
            else:
                # Windows 環境：兩階段下載
                # 階段 1: 使用 gallery-dl --dump-json 獲取 metadata
                print(f"[GALLERY-DL] 階段1: 獲取 metadata...", flush=True)
                metadata_cmd = [
                    sys.executable,
                    '-m', 'gallery_dl',
                    '--dump-json',
                    self.url
                ]
                
                metadata_result = subprocess.run(
                    metadata_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                # 解析並儲存 metadata
                if metadata_result.returncode == 0 and metadata_result.stdout.strip():
                    try:
                        metadata_list = json.loads(metadata_result.stdout)
                        if metadata_list and len(metadata_list) > 0:
                            first_item = metadata_list[0]
                            if isinstance(first_item, list) and len(first_item) >= 2:
                                gallery_metadata = first_item[1]
                            else:
                                gallery_metadata = first_item
                            
                            metadata_file = self.temp_path / "gallery_metadata.json"
                            with open(metadata_file, 'w', encoding='utf-8') as f:
                                json.dump(gallery_metadata, f, ensure_ascii=False, indent=2)
                            print(f"[GALLERY-DL] Metadata 已儲存: {metadata_file}", flush=True)
                    except json.JSONDecodeError as e:
                        print(f"[GALLERY-DL] Metadata 解析失敗: {e}", flush=True)
                
                # 階段 2: 下載圖片
                print(f"[GALLERY-DL] 階段2: 下載圖片...", flush=True)
                
                # 設定檔路徑
                config_path = BASE_DIR / "config" / "gallery-dl.conf"
                
                cmd = [
                    sys.executable,
                    '-m', 'gallery_dl',
                    '--config', str(config_path),
                    '--dest', str(self.temp_path),
                    '--write-metadata',
                    self.url
                ]
                
                logger.info(f"執行指令: {' '.join(cmd)}")
                print(f"[GALLERY-DL] 命令: {cmd}", flush=True)
                
                # 執行 gallery-dl 命令
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=900
                )
            print(f"[GALLERY-DL] 執行完成", flush=True)
            
            # 強制輸出所有 gallery-dl 日誌（用於除錯）
            print(f"[GALLERY-DL] URL: {self.url}", flush=True)
            print(f"[GALLERY-DL] 返回碼: {result.returncode}", flush=True)
            print(f"[GALLERY-DL] STDOUT: {result.stdout[:2000] if result.stdout else '(空)'}", flush=True)
            print(f"[GALLERY-DL] STDERR: {result.stderr[:2000] if result.stderr else '(空)'}", flush=True)
            
            if result.returncode != 0:
                logger.error(f"gallery-dl 返回碼: {result.returncode}")
                logger.error(f"gallery-dl STDERR: {result.stderr}")
                logger.error(f"gallery-dl STDOUT: {result.stdout}")
                
                # 儲存詳細錯誤訊息供 Discord 回報
                # cmd 在 Docker 環境是字串，Windows 環境是列表
                cmd_str = cmd if isinstance(cmd, str) else ' '.join(cmd)
                error_lines = [
                    f"\u26a0\ufe0f **Debug 資訊**",
                    f"\ud83d\udce6 版本: {VERSION}",
                    f"\ud83d\udcbb 環境: {'Docker' if IS_DOCKER else 'Windows'}",
                    f"\ud83d\udcc2 下載目錄: `{self.temp_path}`",
                    f"\ud83d\udd27 執行命令: `{cmd_str}`",
                    f"\ud83d\udd34 返回碼: {result.returncode}",
                ]
                
                if result.stderr:
                    error_lines.append(f"\n**STDERR:**\n```\n{result.stderr[:800]}\n```")
                if result.stdout:
                    error_lines.append(f"\n**STDOUT:**\n```\n{result.stdout[:800]}\n```")
                
                self.last_error = "\n".join(error_lines)
                return False
            
            logger.info(f"gallery-dl 輸出: {result.stdout}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("gallery-dl 執行超時")
            return False
        except Exception as e:
            logger.error(f"gallery-dl 執行錯誤: {e}")
            return False
    
    def convert_to_pdf(self, images: List[Path], output_pdf: Path) -> bool:
        """
        使用 Pillow 將圖片轉換為等寬 PDF（支援進度回報）
        
        所有圖片會被調整為統一寬度（使用最大寬度），高度按比例縮放，
        確保 PDF 每一頁都是 100% 寬度對齊。
        
        Args:
            images: 圖片檔案列表
            output_pdf: 輸出 PDF 路徑
        
        Returns:
            成功返回 True，失敗返回 False
        """
        if not images:
            logger.error("沒有圖片可供轉換")
            return False
        
        try:
            from PIL import Image
            
            self.pdf_converting = True
            self.pdf_progress = 0
            
            # 確保輸出目錄存在
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"轉換 {len(images)} 張圖片為等寬 PDF")
            
            total = len(images)
            
            # 階段 1: 讀取所有圖片並找出最大寬度 (0-20%)
            logger.info("階段 1/3: 分析圖片尺寸...")
            pil_images = []
            max_width = 0
            
            for i, img_path in enumerate(images):
                img = Image.open(img_path)
                # 轉換為 RGB（PDF 不支援 RGBA 透明通道）
                if img.mode in ('RGBA', 'P', 'LA'):
                    # 建立白色背景
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    if img.mode in ('RGBA', 'LA'):
                        background.paste(img, mask=img.split()[-1])  # 使用 alpha 通道作為遮罩
                        img = background
                    else:
                        img = img.convert('RGB')
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                pil_images.append(img)
                if img.width > max_width:
                    max_width = img.width
                
                self.pdf_progress = int((i + 1) / total * 20)
                if (i + 1) % 10 == 0:
                    time.sleep(0.05)
            
            logger.info(f"統一寬度: {max_width}px")
            
            # 階段 2: 調整所有圖片為等寬 (20-70%)
            logger.info("階段 2/3: 調整圖片為等寬...")
            resized_images = []
            
            for i, img in enumerate(pil_images):
                if img.width != max_width:
                    # 按比例縮放到目標寬度
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    # 使用高品質縮放
                    resized_img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    resized_images.append(resized_img)
                else:
                    resized_images.append(img)
                
                self.pdf_progress = 20 + int((i + 1) / total * 50)
                if (i + 1) % 10 == 0:
                    time.sleep(0.05)
            
            # 階段 3: 儲存為 PDF (70-100%)
            logger.info("階段 3/3: 生成 PDF...")
            logger.info(f"PDF 輸出路徑: {output_pdf}")
            logger.info(f"路徑長度: {len(str(output_pdf))} 字元")
            self.pdf_progress = 75
            
            # 第一張圖片作為基底，其餘 append
            first_image = resized_images[0]
            rest_images = resized_images[1:] if len(resized_images) > 1 else []
            
            try:
                first_image.save(
                    output_pdf,
                    "PDF",
                    save_all=True,
                    append_images=rest_images,
                    resolution=100.0
                )
                logger.info("PDF save 呼叫完成")
            except Exception as save_error:
                logger.error(f"PDF save 失敗: {save_error}")
                import traceback
                logger.error(traceback.format_exc())
                self.pdf_converting = False
                return False
            
            # 清理記憶體 - 使用 set 追蹤已關閉的圖片 id，避免比較操作
            closed_ids = set()
            for img in pil_images:
                if id(img) not in closed_ids:
                    try:
                        img.close()
                    except Exception:
                        pass
                    closed_ids.add(id(img))
            for img in resized_images:
                if id(img) not in closed_ids:
                    try:
                        img.close()
                    except Exception:
                        pass
                    closed_ids.add(id(img))
            
            self.pdf_progress = 100
            self.pdf_converting = False
            
            # 確認 PDF 已生成
            if output_pdf.exists() and output_pdf.stat().st_size > 0:
                logger.info(f"PDF 生成成功: {output_pdf}")
                return True
            else:
                logger.error("PDF 檔案未生成或為空")
                return False
                
        except Exception as e:
            logger.error(f"PDF 轉換錯誤: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.pdf_converting = False
            return False
    
    def process(self) -> tuple[bool, str]:
        """
        執行完整的下載處理流程
        
        Returns:
            (成功狀態, 結果訊息)
        """
        start_time = time.time()  # 開始計時
        
        try:
            # 檢查是否已被取消
            if self.is_cancelled():
                return False, "🚫 下載已取消"
            
            # 步驟 1: 下載
            logger.info(f"開始下載: {self.url}")
            print(f"[PROCESS] 開始下載: {self.url}", flush=True)
            if not self.download_with_gallery_dl():
                # 再次檢查是否被取消
                if self.is_cancelled():
                    return False, "🚫 下載已取消"
                error_detail = self.last_error if self.last_error else "未知原因"
                elapsed = time.time() - start_time
                return False, f"❌ 下載失敗\n🔗 {self.url}\n⏱️ 耗時: {elapsed:.1f}s\n\n{error_detail}"
            
            # 檢查是否已被取消
            if self.is_cancelled():
                return False, "🚫 下載已取消"
            
            # 尋找下載的內容
            # gallery-dl 可能會建立子目錄
            print(f"[PROCESS] 搜尋圖片目錄: {self.temp_path}", flush=True)
            images = find_images(self.temp_path)
            print(f"[PROCESS] 找到 {len(images)} 張圖片", flush=True)
            
            if not images:
                # 列出目錄內容以便除錯
                try:
                    all_files = list(self.temp_path.rglob('*'))
                    print(f"[DEBUG] 目錄內所有檔案: {[str(f) for f in all_files[:20]]}", flush=True)
                except Exception as e:
                    print(f"[DEBUG] 無法列出目錄: {e}", flush=True)
                elapsed = time.time() - start_time
                return False, f"❌ 找不到下載的圖片\n🔗 {self.url}\n⏱️ 耗時: {elapsed:.1f}s"
            
            logger.info(f"找到 {len(images)} 張圖片")
            
            # 步驟 2: 解析 metadata
            info_json = find_info_json(self.temp_path)
            
            if info_json:
                metadata = parse_gallery_dl_info(info_json)
            else:
                logger.warning("找不到 info.json，使用預設 metadata")
                metadata = None
            
            # 設定標題 - 優先使用日文標題
            if metadata:
                # 優先順序: 日文標題 > 英文標題 > URL ID
                if metadata.get('title_japanese'):
                    title = metadata['title_japanese']
                    logger.info(f"使用日文標題: {title}")
                elif metadata.get('title'):
                    title = metadata['title']
                    logger.info(f"使用英文標題: {title}")
                else:
                    title = None
            else:
                title = None
            
            # 提取 gallery_id 用於目錄和檔名（避免路徑過長）
            gallery_id_for_path = metadata.get('gallery_id', '') if metadata else ''
            if not gallery_id_for_path:
                # 嘗試從 URL 提取
                match = re.search(r'/g/(\d+)', self.url)
                if match:
                    gallery_id_for_path = match.group(1)
                else:
                    gallery_id_for_path = str(int(time.time()))
            
            if not title:
                title = f"Gallery_{gallery_id_for_path}"
            
            safe_title = sanitize_filename(title)
            logger.info(f"使用標題: {safe_title}")
            logger.info(f"使用 Gallery ID 作為目錄名: {gallery_id_for_path}")
            
            # 建立輸出資料夾 - 使用 gallery_id 避免路徑過長
            self.output_path = DOWNLOAD_DIR / gallery_id_for_path
            
            # 如果資料夾已存在，使用時間戳命名避免覆蓋
            if self.output_path.exists():
                self.output_path = DOWNLOAD_DIR / f"{gallery_id_for_path}_{int(time.time())}"
                logger.info(f"資料夾已存在，使用新資料夾 {self.output_path}")
            
            self.output_path.mkdir(parents=True, exist_ok=True)
            
            # 步驟 3: 轉換為 PDF - 使用 gallery_id 作為檔名
            pdf_path = self.output_path / f"{gallery_id_for_path}.pdf"
            if not self.convert_to_pdf(images, pdf_path):
                return False, "❌ PDF 轉換失敗"
            
            # 步驟 3.5: 複製第一張圖片作為封面
            if images:
                try:
                    first_image = images[0]
                    # 獲取副檔名
                    ext = first_image.suffix  # 例如 .jpg, .png
                    cover_path = self.output_path / f"cover{ext}"
                    # 複製第一張圖片
                    shutil.copy2(first_image, cover_path)
                    logger.info(f"封面已保存: {cover_path.name}")
                except Exception as e:
                    logger.warning(f"保存封面失敗: {e}")
            
            # 步驟 4: 獲取額外資訊（收藏數、評論）
            gallery_id = metadata.get('gallery_id', '') if metadata else ''
            if not gallery_id:
                # 嘗試從 URL 提取
                match = re.search(r'/g/(\d+)', self.url)
                if match:
                    gallery_id = match.group(1)
            
            nhentai_extra = {}
            if gallery_id:
                logger.info(f"獲取 nhentai 額外資訊 (ID: {gallery_id})...")
                nhentai_extra = fetch_nhentai_extra_info(gallery_id)
            
            # 步驟 5: 生成 Eagle metadata（包含擴展資訊）
            extra_info = None
            if metadata:
                extra_info = {
                    'title_japanese': metadata.get('title_japanese', ''),
                    'title_english': metadata.get('title', ''),  # 英文標題放 annotation
                    'title_pretty': metadata.get('title_pretty', ''),
                    'gallery_id': metadata.get('gallery_id', ''),
                    'pages': metadata.get('pages', 0),
                    'favorites': nhentai_extra.get('favorites', 0),  # 從 API 獲取
                    'category': metadata.get('category', ''),
                    'type': metadata.get('type', ''),
                    'artist': metadata.get('artist', []),
                    'group': metadata.get('group', []),
                    'parody': metadata.get('parody', []),
                    'character': metadata.get('character', []),
                    'language': metadata.get('language', ''),
                    'comments': nhentai_extra.get('comments', []),  # 評論
                }
            
            eagle_metadata = create_eagle_metadata(
                title=title,  # 已經是日文標題優先
                url=metadata.get('url', self.url) if metadata else self.url,
                tags=metadata.get('tags', []) if metadata else [],
                annotation="",
                extra_info=extra_info
            )
            
            # 確保輸出目錄存在（防止 UNC 路徑問題）
            self.output_path.mkdir(parents=True, exist_ok=True)
            
            metadata_path = self.output_path / "metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(eagle_metadata, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Eagle metadata 已生成: {metadata_path}")
            
            # 步驟 5: 清理暫存檔案
            if self.temp_path and self.temp_path.exists():
                shutil.rmtree(self.temp_path)
                logger.info(f"已清理暫存目錄: {self.temp_path}")
            
            # 計算耗時
            elapsed = time.time() - start_time
            if elapsed >= 60:
                elapsed_str = f"{int(elapsed // 60)}分{int(elapsed % 60)}秒"
            else:
                elapsed_str = f"{elapsed:.1f}秒"
            
            # 獲取頁數
            page_count = metadata.get('pages', len(images)) if metadata else len(images)
            
            # 轉換路徑為字串，確保 UNC 路徑正確顯示
            output_path_str = str(self.output_path)
            if output_path_str.startswith('\\\\'):
                output_path_str = output_path_str  # 已經是正確的 UNC 路徑
            elif output_path_str.startswith('\\') and not output_path_str.startswith('\\\\'):
                output_path_str = '\\' + output_path_str  # 補上缺少的斜線
            
            # 生成 PDF Web 連結 - 使用實際資料夾名稱（可能有時間戳後綴）
            from urllib.parse import quote
            folder_name = self.output_path.name  # 使用實際資料夾名稱
            pdf_filename = f"{gallery_id_for_path}.pdf"
            pdf_web_url = f"{PDF_WEB_BASE_URL}/{quote(folder_name)}/{quote(pdf_filename)}"
            
            # 使用純 URL 顯示（避免 markdown 連結被編碼的括號破壞）
            return True, f"✅ 完成: **{safe_title}**\n📄 {page_count}頁 ⏱️ {elapsed_str}\n📥 {pdf_web_url}\n📁 {output_path_str}"
            
        except Exception as e:
            logger.exception(f"處理過程發生錯誤: {e}")
            
            # 計算耗時
            elapsed = time.time() - start_time
            
            # 清理暫存檔案
            if self.temp_path and self.temp_path.exists():
                try:
                    shutil.rmtree(self.temp_path)
                except Exception:
                    pass
            
            return False, f"❌ 錯誤: {str(e)}\n⏱️ 耗時: {elapsed:.1f}s"


# ==================== Worker Thread ====================

class DownloadWorker(threading.Thread):
    """
    下載工作執行緒：從佇列中取出任務並執行
    """
    
    def __init__(self, bot):
        super().__init__(daemon=True)
        self.bot = bot
        self.running = True
        self.current_task: Optional[str] = None  # 正在處理的 URL
    
    def run(self):
        """工作執行緒主迴圈"""
        logger.info("下載工作執行緒已啟動")
        
        while self.running:
            try:
                # 從佇列取得任務（阻塞式等待，1秒超時）
                task = download_queue.get(timeout=1)
                
                if task is None:
                    continue
                
                # 支援格式: 
                # (url, channel_id)
                # (url, channel_id, status_msg_id)
                # (url, channel_id, status_msg_id, test_mode)
                # (url, channel_id, status_msg_id, test_mode, batch_id)
                batch_id = None
                if len(task) == 5:
                    url, channel_id, status_msg_id, test_mode, batch_id = task
                elif len(task) == 4:
                    url, channel_id, status_msg_id, test_mode = task
                elif len(task) == 3:
                    url, channel_id, status_msg_id = task
                    test_mode = False
                else:
                    url, channel_id = task
                    status_msg_id = None
                    test_mode = False
                
                self.current_task = url
                logger.info(f"處理下載任務: {url}")
                
                # 提取 gallery ID 並獲取頁數，發送開始訊息
                start_msg_id = None
                pages = 0
                title = ""
                media_id = ""
                current_gallery_id = None
                cancel_event = None
                match = re.search(r'/g/(\d+)', url)
                if match:
                    current_gallery_id = match.group(1)
                    gallery_id = current_gallery_id
                    
                    # 註冊取消事件
                    cancel_event = register_cancel_event(gallery_id)
                    
                    pages, title, media_id = get_nhentai_page_count(gallery_id)
                    if pages > 0:
                        # 發送開始下載訊息（包含頁數和預估時間），並返回訊息 ID
                        future = asyncio.run_coroutine_threadsafe(
                            self.send_start_message(channel_id, gallery_id, pages, title, media_id),
                            self.bot.loop
                        )
                        start_msg_id = future.result(timeout=10)
                
                # 檢查是否在開始前就被取消
                if current_gallery_id and is_cancelled(current_gallery_id):
                    logger.info(f"下載已取消 (開始前): {current_gallery_id}")
                    unregister_cancel_event(current_gallery_id)
                    self.current_task = None
                    download_queue.task_done()
                    continue
                
                # 創建下載處理器（傳入取消事件）
                processor = DownloadProcessor(url, total_pages=pages, cancel_event=cancel_event)
                
                # 啟動進度監控執行緒
                progress_stop_event = threading.Event()
                if start_msg_id and pages > 0:
                    progress_thread = threading.Thread(
                        target=self._monitor_progress,
                        args=(processor, channel_id, start_msg_id, pages, title, gallery_id, media_id, progress_stop_event),
                        daemon=True
                    )
                    progress_thread.start()
                
                # 執行下載處理
                success, message = processor.process()
                
                # 檢查是否被取消
                was_cancelled = current_gallery_id and is_cancelled(current_gallery_id)
                if was_cancelled:
                    success = False
                    message = f"🚫 下載已取消: #{current_gallery_id}"
                
                # 取消註冊取消事件
                if current_gallery_id:
                    unregister_cancel_event(current_gallery_id)
                
                # 停止進度監控
                progress_stop_event.set()
                
                # 更新開始下載訊息（顯示最終狀態）
                if start_msg_id and not was_cancelled:
                    asyncio.run_coroutine_threadsafe(
                        self.update_final_progress(channel_id, start_msg_id, success, pages, title, gallery_id),
                        self.bot.loop
                    )
                
                # 發送結果到 Discord (取消時不發送額外訊息)
                if not was_cancelled:
                    asyncio.run_coroutine_threadsafe(
                        self.send_result(channel_id, message),
                        self.bot.loop
                    )
                
                # 更新批次追蹤
                if batch_id:
                    batch_result = update_batch(batch_id, success, current_gallery_id)
                    if batch_result:
                        # 批次完成，發送總結
                        asyncio.run_coroutine_threadsafe(
                            self.send_batch_summary(batch_result),
                            self.bot.loop
                        )
                
                self.current_task = None
                download_queue.task_done()
            
            except Empty:
                # 佇列為空，這是正常的，繼續等待
                continue
                
            except Exception as e:
                self.current_task = None
                logger.exception(f"工作執行緒錯誤: {e}")
    
    def _monitor_progress(self, processor: DownloadProcessor, channel_id: int, 
                          message_id: int, total_pages: int, title: str, 
                          gallery_id: str, media_id: str, stop_event: threading.Event):
        """
        監控下載進度並更新 Discord 訊息
        
        在背景執行緒中定期檢查已下載的圖片數量，並編輯訊息顯示進度條
        """
        last_count = 0
        last_pdf_progress = -1
        start_time = time.time()
        pdf_start_time = None  # PDF 轉換開始時間
        first_image_sent = False  # 追蹤是否已發送第一張圖片
        pdf_mode = False  # 是否進入 PDF 模式
        
        while not stop_event.is_set():
            try:
                # 根據模式調整檢查間隔
                check_interval = 1 if pdf_mode else PROGRESS_UPDATE_INTERVAL
                
                # 等待一段時間
                if stop_event.wait(timeout=check_interval):
                    break  # 收到停止信號
                
                # 檢查是否在 PDF 轉換階段
                if processor.pdf_converting:
                    pdf_mode = True
                    pdf_progress = processor.pdf_progress
                    
                    # 記錄 PDF 開始時間
                    if pdf_start_time is None:
                        pdf_start_time = time.time()
                    
                    if pdf_progress != last_pdf_progress:
                        last_pdf_progress = pdf_progress
                        
                        # 計算 PDF 預估剩餘時間
                        pdf_eta_str = "計算中..."
                        if pdf_progress > 0:
                            pdf_elapsed = time.time() - pdf_start_time
                            pdf_eta_seconds = (pdf_elapsed / pdf_progress) * (100 - pdf_progress)
                            if pdf_eta_seconds >= 60:
                                pdf_eta_str = f"{int(pdf_eta_seconds // 60)}分{int(pdf_eta_seconds % 60)}秒"
                            else:
                                pdf_eta_str = f"{int(pdf_eta_seconds)}秒"
                        
                        # 顯示 PDF 轉換進度
                        pdf_bar = create_progress_bar(pdf_progress, 100)
                        # 下載進度條保持 100%
                        download_bar = create_progress_bar(total_pages, total_pages)
                        
                        asyncio.run_coroutine_threadsafe(
                            self.update_pdf_progress_message(
                                channel_id, message_id, 
                                pdf_progress, pdf_bar, download_bar, total_pages, title, pdf_eta_str
                            ),
                            self.bot.loop
                        )
                    continue
                
                # 獲取已下載數量
                current_count = processor.get_downloaded_count()
                
                # 等第 3 張圖片下載完成後，發送第一張圖片（確保第一張已完整下載）
                if current_count >= 3 and not first_image_sent:
                    first_image_sent = True
                    # 等待 1 秒確保 NAS 寫入完成
                    time.sleep(1)
                    first_image = processor.get_first_image_path()
                    # 確認檔案大小大於 0
                    if first_image and first_image.exists() and first_image.stat().st_size > 0:
                        asyncio.run_coroutine_threadsafe(
                            self.send_cover_image(channel_id, first_image),
                            self.bot.loop
                        )
                
                # 下載完成時，切換到更頻繁的檢查模式以偵測 PDF 轉換
                if current_count >= total_pages:
                    pdf_mode = True
                
                # 只有進度有變化時才更新
                if current_count != last_count and current_count > 0:
                    last_count = current_count
                    
                    # 計算進度和預估剩餘時間
                    progress_bar = create_progress_bar(current_count, total_pages)
                    elapsed = time.time() - start_time
                    
                    if current_count > 0:
                        avg_time_per_page = elapsed / current_count
                        remaining_pages = total_pages - current_count
                        eta_seconds = remaining_pages * avg_time_per_page
                        
                        if eta_seconds >= 60:
                            eta_str = f"{int(eta_seconds // 60)}分{int(eta_seconds % 60)}秒"
                        else:
                            eta_str = f"{int(eta_seconds)}秒"
                    else:
                        eta_str = "計算中..."
                    
                    # 更新訊息
                    asyncio.run_coroutine_threadsafe(
                        self.update_progress_message(
                            channel_id, message_id, 
                            current_count, total_pages, 
                            progress_bar, eta_str, title
                        ),
                        self.bot.loop
                    )
                    
            except Exception as e:
                logger.error(f"進度監控錯誤: {e}")
    
    async def send_cover_image(self, channel_id: int, image_path: Path):
        """發送封面圖片作為附件"""
        try:
            channel = self.bot.get_channel(channel_id)
            if channel and image_path and image_path.exists():
                await channel.send(file=discord.File(image_path))
                logger.info(f"已發送封面圖片: {image_path.name}")
        except Exception as e:
            logger.error(f"發送封面圖片失敗: {e}")
    
    async def update_progress_message(self, channel_id: int, message_id: int,
                                       current: int, total: int,
                                       progress_bar: str, eta: str, title: str):
        """編輯訊息更新下載進度"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                return
            
            # 編輯訊息
            new_content = (
                f"🔄 下載中...\n"
                f"📖 {title}\n"
                f"{progress_bar}\n"
                f"({current}/{total}) ⏱️ 預估剩餘: {eta}"
            )
            await message.edit(content=new_content)
            
        except Exception as e:
            logger.error(f"更新進度訊息失敗: {e}")
    
    async def update_pdf_progress_message(self, channel_id: int, message_id: int,
                                          progress: int, pdf_bar: str, download_bar: str, 
                                          total_pages: int, title: str, eta: str = ""):
        """編輯訊息更新 PDF 轉換進度"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                return
            
            # 編輯訊息 - 顯示兩條進度條
            new_content = (
                f"📄 製作 PDF 中...\n"
                f"📖 {title}\n"
                f"下載: \n{download_bar}\n"
                f"({total_pages}/{total_pages})\n"
                f"PDF: \n{pdf_bar}\n"
                f"⏱️ 預估剩餘: {eta}"
            )
            await message.edit(content=new_content)
            
        except Exception as e:
            logger.error(f"更新 PDF 進度訊息失敗: {e}")
    
    async def update_final_progress(self, channel_id: int, message_id: int, 
                                    success: bool, total: int, title: str, gallery_id: str = ""):
        """更新最終進度狀態"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                return
            
            # 更新訊息內容和表情
            if success:
                progress_bar = create_progress_bar(total, total)
                
                # 建立下載完成互動視圖
                from bot.views import DownloadCompleteView
                view = DownloadCompleteView(
                    gallery_id=gallery_id if gallery_id else "unknown",
                    title=title
                )
                
                await message.edit(
                    content=f"✅ 下載完成\n📖 {title}\n{progress_bar}\n({total}/{total})",
                    view=view
                )
                await message.add_reaction('✅')
            else:
                await message.add_reaction('❌')
            
        except Exception as e:
            logger.error(f"更新最終進度失敗: {e}")
    
    async def send_start_message(self, channel_id: int, gallery_id: str, pages: int, title: str, media_id: str = "") -> int:
        """
        發送開始下載訊息（包含頁數和預估時間 + 取消按鈕）
        
        Returns:
            訊息 ID，失敗時返回 None
        """
        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                # 計算預估時間
                est_seconds = pages * SECONDS_PER_PAGE
                if est_seconds >= 60:
                    est_str = f"{int(est_seconds // 60)}分{int(est_seconds % 60)}秒"
                else:
                    est_str = f"{int(est_seconds)}秒"
                
                # 初始進度條
                progress_bar = create_progress_bar(0, pages)
                
                # 建立帶有取消按鈕的 View
                from bot.views import DownloadProgressView
                view = DownloadProgressView(gallery_id=gallery_id, title=title)
                
                # 發送進度訊息
                msg = await channel.send(
                    f"🔄 開始下載 **#{gallery_id}**\n"
                    f"📖 {title}\n"
                    f"{progress_bar}\n"
                    f"(0/{pages}) ⏱️ 預估: {est_str}",
                    view=view
                )
                
                return msg.id
        except Exception as e:
            logger.error(f"發送開始訊息失敗: {e}")
        return None
    
    async def update_status_reaction(self, channel_id: int, message_id: int, success: bool):
        """更新狀態訊息的表情：添加 ✅ 或 ❌（已不再使用，保留兼容性）"""
        if not message_id:
            return
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                return
            
            # 添加結果表情
            result_emoji = '✅' if success else '❌'
            await message.add_reaction(result_emoji)
            
        except Exception as e:
            logger.error(f"更新狀態表情失敗: {e}")
    
    async def send_result(self, channel_id: int, message: str):
        """發送結果訊息到 Discord 頻道"""
        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(message)
        except Exception as e:
            logger.error(f"發送訊息失敗: {e}")
    
    async def send_batch_summary(self, batch_result: Dict[str, Any]):
        """發送批次下載完成總結"""
        try:
            channel = self.bot.get_channel(batch_result['channel_id'])
            if not channel:
                return
            
            total = batch_result['total']
            success = batch_result['success']
            failed = batch_result['failed']
            
            # 構建總結訊息
            if failed == 0:
                emoji = "🎉"
                status = "全部成功"
            elif success == 0:
                emoji = "❌"
                status = "全部失敗"
            else:
                emoji = "⚠️"
                status = "部分完成"
            
            msg_lines = [
                f"{emoji} **批次下載完成** - {status}",
                f"",
                f"📊 **統計結果**",
                f"• 總計: {total} 個",
                f"• ✅ 成功: {success} 個",
                f"• ❌ 失敗: {failed} 個",
            ]
            
            # 如果有失敗的，列出失敗的 ID
            if batch_result.get('failed_ids'):
                failed_ids = batch_result['failed_ids'][:10]  # 最多顯示 10 個
                failed_list = ", ".join([f"`{gid}`" for gid in failed_ids])
                msg_lines.append(f"")
                msg_lines.append(f"❌ 失敗清單: {failed_list}")
                if len(batch_result['failed_ids']) > 10:
                    msg_lines.append(f"... 及其他 {len(batch_result['failed_ids']) - 10} 個")
            
            await channel.send("\n".join(msg_lines))
            logger.info(f"批次下載完成: {success}/{total} 成功")
            
        except Exception as e:
            logger.error(f"發送批次總結失敗: {e}")
    
    def stop(self):
        """停止工作執行緒"""
        self.running = False


# ==================== Discord Bot ====================

class HentaiFetcherBot(commands.Bot):
    """
    HentaiFetcher Discord Bot (使用 Slash Commands)
    """
    
    def __init__(self):
        # 設定 Intents
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None  # 使用自訂 help
        )
        
        self.worker: Optional[DownloadWorker] = None
    
    async def setup_hook(self):
        """Bot 啟動時的設定"""
        # 啟動工作執行緒
        self.worker = DownloadWorker(self)
        self.worker.start()
        logger.info("Bot setup 完成，下載執行緒已啟動")
    
    async def on_guild_join(self, guild):
        """加入新伺服器時同步指令"""
        try:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"已同步 {len(synced)} 個斜線指令到新伺服器: {guild.name}")
        except Exception as e:
            logger.error(f"同步斜線指令到 {guild.name} 失敗: {e}")
    
    async def on_ready(self):
        """Bot 連線成功時觸發"""
        logger.info(f'Bot 已登入: {self.user.name} (ID: {self.user.id})')
        logger.info(f'已連接到 {len(self.guilds)} 個伺服器')
        
        # 同步斜線指令到所有已加入的伺服器（即時生效）
        try:
            for guild in self.guilds:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ 已同步 {len(synced)} 個斜線指令到: {guild.name}")
        except Exception as e:
            logger.error(f"同步斜線指令失敗: {e}")
        
        # 設定狀態
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="#hentaifetcher"
            )
        )
        
        # 顯示專用頻道設定
        logger.info(f"專用頻道名稱: {DEDICATED_CHANNEL_NAMES}")
        logger.info("✅ Bot 已就緒！在專用頻道直接貼網址或數字即可下載")
    
    async def on_message(self, message):
        """處理訊息 - 支援專用頻道（不需 !dl）和傳統指令模式"""
        # 忽略 Bot 自己的訊息
        if message.author.bot:
            return
        
        # 訊息去重 - 避免重複處理
        if is_message_processed(message.id):
            print(f"[DEBUG] 跳過重複訊息: {message.id}", flush=True)
            return
        
        content = message.content.strip()
        
        # 忽略空訊息
        if not content:
            return
        
        # 檢查是否在專用頻道中
        is_dedicated_channel = (
            message.channel.name.lower() in [n.lower() for n in DEDICATED_CHANNEL_NAMES] or
            message.channel.id in DEDICATED_CHANNEL_IDS
        )
        
        # Debug: 記錄收到的訊息
        if is_dedicated_channel:
            print(f"[專用頻道] 收到訊息 (ID:{message.id}): {repr(content[:100])}", flush=True)
        else:
            print(f"[DEBUG] 收到訊息 (ID:{message.id}): {repr(content[:100])}", flush=True)
        
        # ===== 專用頻道模式：不需要 !dl 前綴 =====
        if is_dedicated_channel:
            # 忽略斜線指令（由 Discord 處理）
            if content.startswith('/'):
                return
            
            # 忽略 ! 前綴（舊指令格式，提示用戶使用斜線指令）
            if content.startswith('!'):
                await message.channel.send("💡 請使用斜線指令，例如：`/help`、`/search`")
                return
            
            # test 模式 - 強制重新下載
            content_lower = content.lower().strip()
            if content_lower.startswith('test ') or content_lower == 'test':
                test_content = content[4:].strip() if len(content) > 4 else ''
                if not test_content:
                    await message.channel.send(
                        "🧪 **Test 模式使用方式（強制重新下載）**\n"
                        "```\n"
                        "test 421633\n"
                        "```\n"
                        "⚠️ 此模式會跳過重複檢查"
                    )
                    return
                
                # 解析 test 內容
                test_urls = parse_input_to_urls(test_content)
                if not test_urls:
                    await message.channel.send(f"⚠️ 無法解析: `{test_content[:50]}`")
                    return
                
                # 加入佇列（test 模式）
                queue_size = download_queue.qsize() + len(test_urls)
                gallery_ids = []
                for url in test_urls:
                    match = re.search(r'/g/(\d+)', url)
                    if match:
                        gallery_ids.append(match.group(1))
                
                if len(test_urls) == 1 and gallery_ids:
                    await message.channel.send(f"🧪 **#{gallery_ids[0]}** 已加入佇列（Test 模式）\n📊 佇列: {queue_size}")
                    batch_id = None
                else:
                    id_list = ", ".join([f"`{gid}`" for gid in gallery_ids[:10]])
                    await message.channel.send(f"🧪 **{len(gallery_ids)}** 個已加入佇列（Test 模式）\n🔢 {id_list}\n📊 佇列: {queue_size}")
                    # 多個下載啟用批次追蹤
                    batch_id = generate_batch_id()
                    init_batch(batch_id, len(test_urls), message.channel.id, gallery_ids)
                
                for url in test_urls:
                    download_queue.put((url, message.channel.id, None, True, batch_id))
                
                logger.info(f"[專用頻道] 新增 {len(test_urls)} 個 TEST 下載任務 (來自: {message.author})" + (f" [批次: {batch_id}]" if batch_id else ""))
                return
            
            # 處理下載請求（直接貼號碼或網址）
            await self.handle_direct_download(message, content)
            return
        
        # ===== 非專用頻道：提示使用斜線指令 =====
        if content.startswith('!'):
            await message.channel.send("💡 請使用斜線指令，例如：`/dl`、`/help`、`/search`")
            return
    
    async def handle_direct_download(self, message, content: str):
        """
        處理專用頻道中的直接下載請求
        不需要 ! 前綴，直接貼網址、數字或指令即可
        """
        content_lower = content.lower().strip()
        
        # ===== 處理指令（不需要 ! 前綴）=====
        # help / h
        if content_lower in ['help', 'h']:
            ctx = await self.get_context(message)
            ctx.command = self.get_command('help')
            await self.invoke(ctx)
            return
        
        # queue / q
        if content_lower in ['queue', 'q']:
            ctx = await self.get_context(message)
            ctx.command = self.get_command('queue')
            await self.invoke(ctx)
            return
        
        # status
        if content_lower == 'status':
            ctx = await self.get_context(message)
            ctx.command = self.get_command('status')
            await self.invoke(ctx)
            return
        
        # ping
        if content_lower == 'ping':
            ctx = await self.get_context(message)
            ctx.command = self.get_command('ping')
            await self.invoke(ctx)
            return
        
        # version / v
        if content_lower in ['version', 'v']:
            ctx = await self.get_context(message)
            ctx.command = self.get_command('version')
            await self.invoke(ctx)
            return
        
        # list / ls / library
        if content_lower in ['list', 'ls', 'library']:
            ctx = await self.get_context(message)
            ctx.command = self.get_command('list')
            await self.invoke(ctx)
            return
        
        # cleanup / clean / dedup
        if content_lower in ['cleanup', 'clean', 'dedup']:
            ctx = await self.get_context(message)
            ctx.command = self.get_command('cleanup')
            await self.invoke(ctx)
            return
        
        # fixcover / fc / addcover
        if content_lower in ['fixcover', 'fc', 'addcover']:
            ctx = await self.get_context(message)
            ctx.command = self.get_command('fixcover')
            await self.invoke(ctx)
            return
        
        # random / rand / r [数量]
        if content_lower.startswith('random ') or content_lower.startswith('rand ') or content_lower.startswith('r ') or content_lower in ['random', 'rand', 'r']:
            # 提取数量参数
            parts = content.split()
            count = 1
            if len(parts) > 1:
                try:
                    count = int(parts[1])
                except:
                    count = 1
            
            # 直接调用函数
            ctx = await self.get_context(message)
            await random_command(ctx, count)
            return
        
        # dl <內容> - 也支援不帶 ! 的 dl
        if content_lower.startswith('dl ') or content_lower == 'dl':
            content = content[2:].strip() if len(content) > 2 else ''
            if not content:
                await message.channel.send(
                    "📖 **下載使用方式**\n"
                    "直接貼網址或號碼即可！\n"
                    "```\n"
                    "421633\n"
                    "421633 607769 613358\n"
                    "https://nhentai.net/g/421633/\n"
                    "```"
                )
                return
        
        # test <內容> - 強制重新下載
        if content_lower.startswith('test ') or content_lower == 'test':
            test_content = content[4:].strip() if len(content) > 4 else ''
            if not test_content:
                await message.channel.send(
                    "🧪 **Test 模式使用方式（強制重新下載）**\n"
                    "```\n"
                    "test 421633\n"
                    "test https://nhentai.net/g/421633/\n"
                    "```\n"
                    "⚠️ 此模式會跳過重複檢查"
                )
                return
            
            # 解析 test 內容
            test_urls = parse_input_to_urls(test_content)
            if not test_urls:
                await message.channel.send(f"⚠️ 無法解析: `{test_content[:50]}`")
                return
            
            # 加入佇列（test 模式）
            queue_size = download_queue.qsize() + len(test_urls)
            gallery_ids = []
            for url in test_urls:
                match = re.search(r'/g/(\d+)', url)
                if match:
                    gallery_ids.append(match.group(1))
            
            if len(test_urls) == 1 and gallery_ids:
                await message.channel.send(f"🧪 **#{gallery_ids[0]}** 已加入佇列（Test 模式）\n📊 佇列: {queue_size}")
                batch_id = None
            else:
                id_list = ", ".join([f"`{gid}`" for gid in gallery_ids[:10]])
                await message.channel.send(f"🧪 **{len(gallery_ids)}** 個已加入佇列（Test 模式）\n🔢 {id_list}\n📊 佇列: {queue_size}")
                # 多個下載啟用批次追蹤
                batch_id = generate_batch_id()
                init_batch(batch_id, len(test_urls), message.channel.id, gallery_ids)
            
            for url in test_urls:
                download_queue.put((url, message.channel.id, None, True, batch_id))
            
            logger.info(f"[專用頻道] 新增 {len(test_urls)} 個 TEST 下載任務 (來自: {message.author})" + (f" [批次: {batch_id}]" if batch_id else ""))
            return
        
        # 解析輸入
        parsed_urls = parse_input_to_urls(content)
        
        if not parsed_urls:
            # 如果無法解析，靜默忽略（不發送錯誤訊息，避免打擾）
            # 但如果內容看起來像是想要下載（純數字或包含 nhentai），給予提示
            if re.search(r'\d{4,7}', content) or 'nhentai' in content.lower():
                await message.channel.send(f"⚠️ 無法解析: `{content[:50]}`\n請確認格式正確（例如: `607769` 或 `https://nhentai.net/g/607769/`）")
            return
        
        # 去除重複 URL (依據 gallery_id)
        seen_ids = set()
        unique_urls = []
        for url in parsed_urls:
            match = re.search(r'/g/(\d+)', url)
            if match:
                gid = match.group(1)
                if gid not in seen_ids:
                    seen_ids.add(gid)
                    unique_urls.append(url)
            else:
                unique_urls.append(url)  # 無法解析的保留
        
        parsed_urls = unique_urls
        
        # 驗證並加入佇列
        valid_urls = []
        invalid_urls = []
        already_exists = []
        
        # 添加 reaction 表示處理中
        try:
            await message.add_reaction('⏳')
        except:
            pass
        
        # 下載前先執行快速 reindex (首個 URL)
        first_check = True
        
        for url in parsed_urls:
            # 提取 gallery ID
            match = re.search(r'/g/(\d+)', url)
            if match:
                gallery_id = match.group(1)
                
                # 先檢查是否已下載 (首個 URL 時觸發 reindex)
                exists, exist_info = check_already_downloaded(gallery_id, do_reindex=first_check)
                first_check = False  # 後續不再 reindex
                
                if exists:
                    already_exists.append((gallery_id, exist_info))
                    continue
                
                # 驗證是否可訪問
                is_valid, info = verify_nhentai_url(gallery_id)
                
                if is_valid:
                    valid_urls.append((url, gallery_id, info))
                else:
                    invalid_urls.append((gallery_id, info))
            else:
                invalid_urls.append((url, "無效格式"))
        
        # 移除處理中 reaction
        try:
            await message.remove_reaction('⏳', self.user)
        except:
            pass
        
        # 回報已存在的項目
        if already_exists:
            if len(already_exists) == 1:
                gid, info = already_exists[0]
                title = info.get('title', '')[:40]
                web_url = info.get('web_url', '')
                await message.channel.send(f"📚 **#{gid}** 已存在\n📖 {title}\n🔗 {web_url}")
            else:
                exist_list = "\n".join([f"• `{gid}`: {info.get('title', '')[:30]}" for gid, info in already_exists[:5]])
                await message.channel.send(f"📚 **{len(already_exists)}** 個已存在（跳過）:\n{exist_list}")
        
        # 處理無效的 URL
        if invalid_urls:
            error_list = "\n".join([f"• `{id}`: {reason}" for id, reason in invalid_urls[:5]])
            await message.channel.send(f"❌ 以下無法下載:\n{error_list}")
        
        # 加入有效的 URL
        if valid_urls:
            queue_size = download_queue.qsize() + len(valid_urls)
            gallery_id_list = [gid for _, gid, _ in valid_urls]
            
            # 發送簡化的狀態訊息（只顯示號碼）
            if len(valid_urls) == 1:
                _, gallery_id, _ = valid_urls[0]
                await message.channel.send(f"📥 **#{gallery_id}** 已加入佇列\n📊 佇列: {queue_size}")
                batch_id = None
            else:
                id_list = ", ".join([f"`{gid}`" for _, gid, _ in valid_urls[:10]])
                await message.channel.send(f"📥 **{len(valid_urls)}** 個已加入佇列\n🔢 {id_list}\n📊 佇列: {queue_size}")
                # 多個下載啟用批次追蹤
                batch_id = generate_batch_id()
                init_batch(batch_id, len(valid_urls), message.channel.id, gallery_id_list)
            
            # 添加成功 reaction 到原始訊息
            try:
                await message.add_reaction('✅')
            except:
                pass
            
            # 加入佇列（包含 batch_id）
            for url, gallery_id, title in valid_urls:
                download_queue.put((url, message.channel.id, None, False, batch_id))
            
            logger.info(f"[專用頻道] 新增 {len(valid_urls)} 個下載任務 (來自: {message.author})" + (f" [批次: {batch_id}]" if batch_id else ""))
    
    async def on_command_error(self, ctx, error):
        """全域錯誤處理"""
        if isinstance(error, commands.CommandNotFound):
            return  # 忽略未知指令
        
        logger.error(f"指令錯誤: {error}")
        await ctx.send(f"⚠️ 發生錯誤: {str(error)}")


# 建立 Bot 實例
bot = HentaiFetcherBot()


# ==================== 斜線指令 ====================

@bot.tree.command(name='dl', description='下載 nhentai 本子')
@app_commands.describe(
    gallery_ids='一個或多個 nhentai 號碼，用空格分隔',
    force='強制重新下載（跳過重複檢查）'
)
async def dl_command(interaction: discord.Interaction, gallery_ids: str, force: bool = False):
    """下載 nhentai 本子"""
    await interaction.response.defer()
    
    # 解析輸入
    parsed_urls = parse_input_to_urls(gallery_ids)
    
    if not parsed_urls:
        await interaction.followup.send("⚠️ 無法解析輸入。請提供有效的 nhentai 號碼。")
        return
    
    # 去除重複 URL (依據 gallery_id)
    seen_ids = set()
    unique_urls = []
    for url in parsed_urls:
        match = re.search(r'/g/(\d+)', url)
        if match:
            gid = match.group(1)
            if gid not in seen_ids:
                seen_ids.add(gid)
                unique_urls.append(url)
        else:
            unique_urls.append(url)
    parsed_urls = unique_urls
    
    # 如果不是強制模式，檢查重複
    new_urls = []
    already_exists = []
    
    if not force:
        # 下載前先執行快速 reindex (首個 URL)
        first_check = True
        
        for url in parsed_urls:
            match = re.search(r'/g/(\d+)', url)
            if match:
                gallery_id = match.group(1)
                # 首個 URL 時觸發 reindex
                exists, info = check_already_downloaded(gallery_id, do_reindex=first_check)
                first_check = False
                
                if exists:
                    already_exists.append((gallery_id, info))
                else:
                    new_urls.append((url, gallery_id))
            else:
                new_urls.append((url, None))
        
        # 回報已存在的項目
        if already_exists:
            if len(already_exists) == 1:
                gid, info = already_exists[0]
                title = info.get('title', '')[:40]
                web_url = info.get('web_url', '')
                await interaction.followup.send(f"📚 **#{gid}** 已存在\n📖 {title}\n🔗 {web_url}")
            else:
                exist_list = "\n".join([f"• `{gid}`: {info.get('title', '')[:30]}" for gid, info in already_exists[:5]])
                await interaction.followup.send(f"📚 **{len(already_exists)}** 個已存在（跳過）:\n{exist_list}")
        
        if not new_urls:
            return
    else:
        new_urls = [(url, re.search(r'/g/(\d+)', url).group(1) if re.search(r'/g/(\d+)', url) else None) for url in parsed_urls]
    
    # 加入佇列
    queue_size = download_queue.qsize() + len(new_urls)
    gallery_id_list = [gid for _, gid in new_urls if gid]
    
    mode_str = "（強制模式）" if force else ""
    if len(new_urls) == 1 and gallery_id_list:
        await interaction.followup.send(f"📥 **#{gallery_id_list[0]}** 已加入佇列{mode_str}\n📊 佇列: {queue_size}")
        # 單個下載不需要批次追蹤
        batch_id = None
    else:
        id_list = ", ".join([f"`{gid}`" for gid in gallery_id_list[:10]])
        await interaction.followup.send(f"📥 **{len(gallery_id_list)}** 個已加入佇列{mode_str}\n🔢 {id_list}\n📊 佇列: {queue_size}")
        # 多個下載啟用批次追蹤
        batch_id = generate_batch_id()
        init_batch(batch_id, len(new_urls), interaction.channel_id, gallery_id_list)
    
    # 加入佇列（包含 batch_id）
    for url, _ in new_urls:
        download_queue.put((url, interaction.channel_id, None, force, batch_id))
    
    logger.info(f"新增 {len(new_urls)} 個下載任務 (來自: {interaction.user})" + (f" [批次: {batch_id}]" if batch_id else ""))


@bot.tree.command(name='queue', description='查看下載佇列狀態')
async def queue_command(interaction: discord.Interaction):
    """查看下載佇列"""
    size = download_queue.qsize()
    await interaction.response.send_message(f"📊 佇列中等待任務: {size}")


@bot.tree.command(name='sync', description='強制同步斜線指令（管理員專用）')
async def sync_command(interaction: discord.Interaction):
    """強制同步斜線指令到 Discord"""
    # 檢查權限（只有管理員可以使用）
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ 此指令僅限管理員使用", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        # 同步到當前伺服器
        bot.tree.copy_global_to(guild=interaction.guild)
        synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"✅ 已同步 **{len(synced)}** 個斜線指令到此伺服器\n💡 新參數應該立即生效", ephemeral=True)
        logger.info(f"手動同步指令到 {interaction.guild.name}: {len(synced)} 個")
    except Exception as e:
        await interaction.followup.send(f"❌ 同步失敗: {e}", ephemeral=True)
        logger.error(f"手動同步指令失敗: {e}")


@bot.tree.command(name='ping', description='測試機器人連線')
async def ping_command(interaction: discord.Interaction):
    """測試連線"""
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 Pong! 延遲: {latency}ms")


@bot.tree.command(name='version', description='顯示機器人版本')
async def version_command(interaction: discord.Interaction):
    """顯示版本"""
    await interaction.response.send_message(f"📦 HentaiFetcher 版本: **{VERSION}**")


@bot.tree.command(name='status', description='顯示機器人狀態')
async def status_command(interaction: discord.Interaction):
    """顯示狀態"""
    embed = discord.Embed(
        title="📊 HentaiFetcher Status",
        color=discord.Color.blue()
    )
    embed.add_field(name="佇列任務", value=str(download_queue.qsize()), inline=True)
    embed.add_field(name="延遲", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="伺服器數", value=str(len(bot.guilds)), inline=True)
    
    # 顯示目前下載狀態
    if bot.worker and bot.worker.current_task:
        match = re.search(r'/g/(\d+)', bot.worker.current_task)
        task_id = match.group(1) if match else "..."
        embed.add_field(name="目前下載", value=f"🔄 `{task_id}`", inline=True)
    else:
        embed.add_field(name="目前下載", value="⏳ 等待中", inline=True)
    
    embed.set_footer(text="使用 /dl <號碼> 開始下載")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='list', description='列出所有已下載的本子（包含 Eagle Library）')
async def list_command(interaction: discord.Interaction):
    """列出所有已下載的本子（分頁顯示）"""
    await interaction.response.defer()
    
    try:
        from urllib.parse import quote
        from eagle_library import EagleLibrary
        from bot.views import PaginatedListView
        
        # 收集所有項目
        items = []  # (gallery_id, title, source)
        seen_ids = set()
        
        # 1. 從 Eagle Library 獲取
        try:
            eagle = EagleLibrary()
            eagle_items = eagle.list_all()
            for item in eagle_items:
                nid = item.get('nhentai_id', '')
                title = item.get('title', item.get('folder_name', ''))
                if nid:
                    seen_ids.add(nid)
                    items.append((nid, title, 'eagle'))
        except Exception as e:
            logger.debug(f"Eagle Library 載入失敗: {e}")
        
        # 2. 從 downloads 資料夾獲取（跳過已在 Eagle 中的）
        if DOWNLOAD_DIR.exists():
            folders = [f for f in DOWNLOAD_DIR.iterdir() if f.is_dir()]
            
            for folder in folders:
                folder_name = folder.name
                
                # 嘗試從 metadata.json 獲取 gallery_id
                metadata_path = folder / "metadata.json"
                gallery_id = ""
                title = folder_name
                if metadata_path.exists():
                    try:
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            # 優先從 gallery_id 獲取
                            gallery_id = metadata.get('gallery_id', '')
                            # 如果沒有，從 URL 提取
                            if not gallery_id:
                                url = metadata.get('url', '')
                                match = re.search(r'/g/(\d+)', url)
                                if match:
                                    gallery_id = match.group(1)
                            # 取得標題
                            title = metadata.get('name', folder_name)
                    except:
                        pass
                
                # 只加入不在 Eagle 中的
                if gallery_id and gallery_id not in seen_ids:
                    items.append((gallery_id, title, 'downloads'))
                    seen_ids.add(gallery_id)
                elif not gallery_id:
                    items.append(('', title, 'downloads'))
        
        if not items:
            await interaction.followup.send("📂 目前沒有任何本子")
            return
        
        # 按號碼排序（從小到大）
        items.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)
        
        # 統計來源數量
        eagle_count = sum(1 for _, _, src in items if src == 'eagle')
        downloads_count = sum(1 for _, _, src in items if src == 'downloads')
        
        # 建立分頁視圖
        view = PaginatedListView(
            items=items,
            eagle_count=eagle_count,
            downloads_count=downloads_count
        )
        
        # 發送帶有分頁的嵌入訊息
        await interaction.followup.send(embed=view.get_embed(), view=view)
        
    except Exception as e:
        logger.error(f"列出失敗: {e}")
        await interaction.followup.send(f"❌ 列出失敗: {e}")


def get_all_downloads_items() -> List[Dict[str, Any]]:
    """
    獲取 downloads 資料夾中所有本子的資訊
    
    Returns:
        包含本子資訊的列表
    """
    results = []
    
    if not DOWNLOAD_DIR.exists():
        return results
    
    for folder in DOWNLOAD_DIR.iterdir():
        if not folder.is_dir():
            continue
        
        metadata_path = folder / "metadata.json"
        if not metadata_path.exists():
            continue
        
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # 從 url 提取 gallery_id
            url = metadata.get('url', '')
            match = re.search(r'/g/(\d+)', url)
            gallery_id = match.group(1) if match else folder.name
            
            results.append({
                'title': metadata.get('name', folder.name),
                'nhentai_id': gallery_id,
                'tags': metadata.get('tags', []),
                'folder_path': str(folder),
                'url': url,
                'annotation': metadata.get('annotation', ''),
                'source': 'downloads'
            })
        except Exception as e:
            logger.debug(f"讀取 metadata 失敗 ({folder.name}): {e}")
    
    return results


def search_in_downloads(query: str) -> List[Dict[str, Any]]:
    """
    在 downloads 資料夾中搜尋本子
    
    Args:
        query: 搜尋關鍵字（支援 ID、標題、作者、原作等）
    
    Returns:
        符合條件的本子列表
    """
    import unicodedata
    
    all_items = get_all_downloads_items()
    results = []
    
    # 標準化查詢字串（移除空白、轉小寫）
    query_normalized = unicodedata.normalize('NFKC', query.lower().strip())
    query_parts = query_normalized.split()  # 分割成多個關鍵字
    
    for item in all_items:
        # 構建可搜尋的文字
        searchable_parts = [
            item.get('title', ''),
            item.get('nhentai_id', ''),
            ' '.join(item.get('tags', [])),
            item.get('annotation', '')
        ]
        searchable_text = unicodedata.normalize('NFKC', ' '.join(searchable_parts).lower())
        
        # 檢查是否所有關鍵字都匹配
        if all(part in searchable_text for part in query_parts):
            results.append(item)
    
    return results


def find_item_by_id(gallery_id: str) -> Optional[Dict[str, Any]]:
    """
    用 ID 在雙來源中查找本子
    
    Args:
        gallery_id: nhentai Gallery ID
    
    Returns:
        找到的本子資訊，或 None
    """
    # 1. 先查 Eagle Library
    try:
        from eagle_library import EagleLibrary
        eagle = EagleLibrary()
        result = eagle.find_by_nhentai_id(gallery_id)
        if result:
            result['source'] = 'eagle'
            return result
    except:
        pass
    
    # 2. 再查 downloads 資料夾
    all_downloads = get_all_downloads_items()
    for item in all_downloads:
        if item.get('nhentai_id') == gallery_id:
            return item
    
    return None


def parse_annotation_comments(annotation: str) -> List[Dict[str, str]]:
    """
    從 annotation 中提取用戶評論
    
    Args:
        annotation: metadata 中的 annotation 字串
    
    Returns:
        評論列表，每個元素包含 user 和 content
    """
    comments = []
    if not annotation:
        return comments
    
    # 查找評論區塊
    if '💬 用戶評論:' not in annotation:
        return comments
    
    comment_section = annotation.split('💬 用戶評論:')[1]
    
    # 截取到下一個時間戳記或結尾
    if '⏰' in comment_section:
        comment_section = comment_section.split('⏰')[0]
    
    lines = comment_section.split('\n')
    current_user = None
    current_content = []
    
    for line in lines:
        line = line.strip()
        if not line:
            # 空行：儲存當前評論
            if current_user and current_content:
                comments.append({
                    'user': current_user,
                    'content': ' '.join(current_content)
                })
                current_user = None
                current_content = []
            continue
        
        # 跳過 "還有 X 則評論" 
        if line.startswith('...') and '則評論' in line:
            continue
        
        # 檢查是否為用戶名行 [username] (time ago)
        if line.startswith('[') and ']' in line:
            # 先儲存上一個評論
            if current_user and current_content:
                comments.append({
                    'user': current_user,
                    'content': ' '.join(current_content)
                })
            current_user = line
            current_content = []
        else:
            # 這是評論內容
            current_content.append(line)
    
    # 儲存最後一個評論
    if current_user and current_content:
        comments.append({
            'user': current_user,
            'content': ' '.join(current_content)
        })
    
    return comments


def get_random_from_downloads(count: int = 1) -> List[Dict[str, Any]]:
    """
    從 downloads 資料夾隨機選取本子
    
    Args:
        count: 要選取的數量
    
    Returns:
        包含本子資訊的列表
    """
    import random
    import secrets
    
    results = []
    
    if not DOWNLOAD_DIR.exists():
        return results
    
    # 獲取所有有 metadata.json 的子資料夾
    valid_folders = []
    for folder in DOWNLOAD_DIR.iterdir():
        if folder.is_dir():
            metadata_path = folder / "metadata.json"
            if metadata_path.exists():
                valid_folders.append(folder)
    
    if not valid_folders:
        return results
    
    # 限制數量
    count = min(count, len(valid_folders))
    
    # 使用 secrets 模組進行加密安全的隨機選取（更加隨機）
    selected_indices = set()
    while len(selected_indices) < count:
        idx = secrets.randbelow(len(valid_folders))
        selected_indices.add(idx)
    
    selected_folders = [valid_folders[i] for i in selected_indices]
    
    for folder in selected_folders:
        metadata_path = folder / "metadata.json"
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # 從 url 提取 gallery_id
            url = metadata.get('url', '')
            match = re.search(r'/g/(\d+)', url)
            gallery_id = match.group(1) if match else folder.name
            
            results.append({
                'title': metadata.get('name', folder.name),
                'nhentai_id': gallery_id,
                'tags': metadata.get('tags', []),
                'folder_path': str(folder),
                'url': url,
                'source': 'downloads'
            })
        except Exception as e:
            logger.debug(f"讀取 metadata 失敗 ({folder.name}): {e}")
    
    return results


@bot.tree.command(name='random', description='隨機顯示本子（預設雙來源）')
@app_commands.describe(
    count='顯示數量 (1-5)',
    source='來源：all=全部(預設), eagle=Eagle Library, downloads=下載資料夾'
)
@app_commands.choices(source=[
    app_commands.Choice(name='🔀 全部 (預設)', value='all'),
    app_commands.Choice(name='🦅 Eagle Library', value='eagle'),
    app_commands.Choice(name='📁 下載資料夾', value='downloads'),
])
async def random_command(interaction: discord.Interaction, count: int = 1, source: str = 'all'):
    """隨機顯示本子"""
    await interaction.response.defer()
    
    try:
        from eagle_library import EagleLibrary
        from pathlib import Path
        import re
        import secrets
        
        # 限制數量
        count = max(1, min(count, 5))  # 1-5 本
        
        selected = []
        
        if source == 'eagle':
            # 從 Eagle Library 隨機選取
            eagle = EagleLibrary()
            selected = eagle.get_random(count)
            if not selected:
                await interaction.followup.send("📂 Eagle Library 中沒有任何本子")
                return
        
        elif source == 'downloads':
            # 從 downloads 資料夾隨機選取
            selected = get_random_from_downloads(count)
            if not selected:
                await interaction.followup.send("📂 下載資料夾中沒有任何本子")
                return
        
        elif source == 'all':
            # 從兩個來源合併後隨機選取
            eagle = EagleLibrary()
            eagle_items = eagle.list_all()
            downloads_items = get_random_from_downloads(100)  # 先取得所有 downloads
            
            # 合併兩個來源（去重）
            all_items = []
            seen_ids = set()
            
            for item in eagle_items:
                nid = item.get('nhentai_id')
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    # 轉換格式以便後續處理
                    eagle_result = eagle.find_by_nhentai_id(nid)
                    if eagle_result:
                        eagle_result['source'] = 'eagle'
                        all_items.append(eagle_result)
            
            for item in downloads_items:
                nid = item.get('nhentai_id')
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    item['source'] = 'downloads'
                    all_items.append(item)
            
            if not all_items:
                await interaction.followup.send("📂 沒有任何本子可供選擇")
                return
            
            # 使用 secrets 進行更隨機的選取
            count = min(count, len(all_items))
            selected_indices = set()
            while len(selected_indices) < count:
                idx = secrets.randbelow(len(all_items))
                selected_indices.add(idx)
            selected = [all_items[i] for i in selected_indices]
        
        if not selected:
            await interaction.followup.send("📂 沒有任何本子可供選擇")
            return
        
        # 逐本顯示（先封面，再資訊）- 避免順序錯亂
        from urllib.parse import quote
        
        for idx, item in enumerate(selected):
            title = item.get('title', '未知')
            gallery_id = item.get('nhentai_id', '未知')
            web_url = item.get('web_url', '')
            tags = item.get('tags', [])
            folder_path = item.get('folder_path', '')
            item_source = item.get('source', 'eagle')
            
            # 解析 tags
            artists = [tag.replace('artist:', '') for tag in tags if isinstance(tag, str) and tag.startswith('artist:')]
            parodies = [tag.replace('parody:', '') for tag in tags if isinstance(tag, str) and tag.startswith('parody:')]
            groups = [tag.replace('group:', '') for tag in tags if isinstance(tag, str) and tag.startswith('group:')]
            languages = [tag.replace('language:', '') for tag in tags if isinstance(tag, str) and tag.startswith('language:')]
            other_tags = [tag for tag in tags if isinstance(tag, str) and not any(tag.startswith(prefix) for prefix in ['artist:', 'parody:', 'group:', 'language:', 'type:'])]
            
            # ===== 1. 先發送封面圖片 =====
            cover_sent = False
            if folder_path:
                try:
                    folder = Path(folder_path)
                    # 封面檔名優先順序
                    for cover_name in ['cover.jpg', 'cover.png', 'cover.webp', 'thumbnail.png']:
                        cover_path = folder / cover_name
                        if cover_path.exists():
                            file = discord.File(str(cover_path), filename=cover_name)
                            if idx == 0:
                                await interaction.followup.send(file=file)
                            else:
                                await interaction.channel.send(file=file)
                            cover_sent = True
                            break
                    
                    # 如果沒找到封面，找第一張圖片
                    if not cover_sent:
                        for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                            images = list(folder.glob(ext))
                            if images:
                                images.sort(key=lambda x: x.name)
                                file = discord.File(str(images[0]), filename=images[0].name)
                                if idx == 0:
                                    await interaction.followup.send(file=file)
                                else:
                                    await interaction.channel.send(file=file)
                                cover_sent = True
                                break
                except Exception as e:
                    logger.debug(f"封面發送失敗: {e}")
            
            # ===== 2. 再發送資料訊息 =====
            msg_lines = []
            
            # 來源標記
            source_emoji = "🦅" if item_source == 'eagle' else "📁"
            
            # 號碼
            msg_lines.append(f"{source_emoji} **#{gallery_id}**")
            
            # 標題內嵌連結 (emoji 在連結外部以確保 markdown 格式正確)
            if item_source == 'eagle' and web_url:
                msg_lines.append(f"📖 [{title}]({web_url})")
            elif item_source == 'downloads' and gallery_id:
                pdf_web_url = f"{PDF_WEB_BASE_URL}/{quote(str(gallery_id))}/{quote(str(gallery_id))}.pdf"
                msg_lines.append(f"📖 [{title}]({pdf_web_url})")
            else:
                msg_lines.append(f"📖 **{title}**")
            
            msg_lines.append("")  # 空行
            
            # ===== 顯示所有 metadata =====
            # 來源
            msg_lines.append(f"📦 來源: {'Eagle Library' if item_source == 'eagle' else '下載資料夾'}")
            
            # 基本資訊
            if artists:
                msg_lines.append(f"✍️ 作者: {', '.join(artists)}")
            if groups:
                msg_lines.append(f"👥 社團: {', '.join(groups)}")
            if parodies:
                msg_lines.append(f"🎬 原作: {', '.join(parodies)}")
            if languages:
                msg_lines.append(f"🌐 語言: {', '.join(languages)}")
            
            # 角色
            characters = [tag.replace('character:', '') for tag in tags if isinstance(tag, str) and tag.startswith('character:')]
            if characters:
                msg_lines.append(f"👤 角色: {', '.join(characters)}")
            
            # 類型
            types = [tag.replace('type:', '') for tag in tags if isinstance(tag, str) and tag.startswith('type:')]
            if types:
                msg_lines.append(f"📁 類型: {', '.join(types)}")
            
            # 使用者評論 (從 annotation 中提取，顯示全部)
            annotation = item.get('annotation', '')
            if annotation:
                comments = parse_annotation_comments(annotation)
                if comments:
                    msg_lines.append("")
                    msg_lines.append("💬 評論:")
                    for c in comments:
                        msg_lines.append(f"  **{c['user']}**")
                        if c['content']:
                            msg_lines.append(f"  {c['content']}")
            
            # Tags (顯示全部標籤)
            if other_tags:
                msg_lines.append(f"")
                msg_lines.append(f"🏷️ 標籤: {', '.join([f'`{tag}`' for tag in other_tags])}")
            
            # 發送資料訊息
            final_msg = "\n".join(msg_lines)
            if len(final_msg) > 1900:
                final_msg = final_msg[:1900] + "..."
            
            # 建立隨機結果互動視圖
            from bot.views import RandomResultView
            view = RandomResultView(
                gallery_id=gallery_id,
                title=title,
                item_source=item_source,
                web_url=web_url,
                artists=artists,
                source_filter=source
            )
            
            # 確保封面已發送才發資訊（順序正確）
            await interaction.channel.send(final_msg, view=view)
    
    except ImportError:
        await interaction.followup.send("❌ Eagle Library 模組未安裝")
    except Exception as e:
        logger.error(f"隨機顯示失敗: {e}")
        await interaction.followup.send(f"❌ 隨機顯示失敗: {e}")


@bot.tree.command(name='fixcover', description='為已下載的本子補充封面')
async def fixcover_command(interaction: discord.Interaction):
    """為已有的本子補充封面"""
    await interaction.response.defer()
    
    try:
        if not DOWNLOAD_DIR.exists():
            await interaction.followup.send("📂 下載資料夾不存在")
            return
        
        await interaction.followup.send("🔍 開始掃描並補充封面...")
        
        folders = [f for f in DOWNLOAD_DIR.iterdir() if f.is_dir()]
        fixed_count = 0
        skipped_count = 0
        fallback_count = 0  # 使用第一張圖片作為封面的數量
        failed_count = 0
        
        for folder in folders:
            # 檢查是否已有封面
            has_cover = any(list(folder.glob(f"cover.{ext}")) for ext in ['jpg', 'jpeg', 'png', 'gif', 'webp'])
            
            if has_cover:
                skipped_count += 1
                continue
            
            # 從 metadata.json 獲取 gallery_id
            metadata_path = folder / "metadata.json"
            gallery_id = ""
            
            if metadata_path.exists():
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        # 從 url 提取 gallery_id
                        url = metadata.get('url', '')
                        match = re.search(r'/g/(\d+)', url)
                        if match:
                            gallery_id = match.group(1)
                except Exception as e:
                    logger.error(f"讀取 metadata 失敗 ({folder.name}): {e}")
            
            cover_success = False
            
            if gallery_id:
                # 嘗試從 nhentai 下載封面
                if download_nhentai_cover(gallery_id, folder):
                    fixed_count += 1
                    cover_success = True
                    logger.info(f"補充封面成功 (nhentai 封面): {folder.name}")
                else:
                    # 封面下載失敗，嘗試下載第一頁作為封面
                    await asyncio.sleep(0.3)  # 短暫延遲避免請求太快
                    if download_nhentai_first_page(gallery_id, folder):
                        fallback_count += 1
                        cover_success = True
                        logger.info(f"補充封面成功 (nhentai 第一頁): {folder.name}")
                # 避免請求太頻繁
                await asyncio.sleep(0.5)
            
            # 如果從 nhentai 都失敗，嘗試使用資料夾內的第一張圖片
            if not cover_success:
                first_image = get_first_image_as_cover(folder)
                if first_image:
                    fallback_count += 1
                    cover_success = True
                    logger.info(f"補充封面成功 (本地圖片): {folder.name}")
                else:
                    failed_count += 1
                    logger.warning(f"補充封面失敗 (所有方法都失敗): {folder.name}")
        
        msg = f"✅ 完成！\n"
        msg += f"📥 從 nhentai 封面下載了 {fixed_count} 個\n"
        if fallback_count > 0:
            msg += f"🖼️ 使用備用方案 {fallback_count} 個\n"
        msg += f"⏭️ 跳過 {skipped_count} 個已有封面\n"
        if failed_count > 0:
            msg += f"❌ 失敗 {failed_count} 個"
        await interaction.channel.send(msg)
        
    except Exception as e:
        logger.error(f"補充封面失敗: {e}")
        await interaction.channel.send(f"❌ 補充封面失敗: {e}")


@bot.tree.command(name='cleanup', description='清除 imported 資料夾中已導入 Eagle 的項目')
async def cleanup_command(interaction: discord.Interaction):
    """清除 imported 資料夾中已導入到 Eagle 的項目"""
    await interaction.response.defer()
    
    try:
        # imported 資料夾路徑
        imported_dir = Path(DOWNLOAD_DIR).parent / 'imported'
        
        if not imported_dir.exists():
            await interaction.followup.send("📂 imported 資料夾不存在")
            return
        
        # 獲取 Eagle 索引
        from eagle_library import EagleLibrary
        eagle = EagleLibrary()
        
        # 先執行 reindex 確保索引最新
        await interaction.followup.send("🔄 正在掃描並比對 Eagle Library...")
        eagle.rebuild_index()
        
        folders = [f for f in imported_dir.iterdir() if f.is_dir()]
        can_delete = []  # 可以刪除的資料夾 (已在 Eagle 中)
        not_in_eagle = []  # 不在 Eagle 中的資料夾
        
        for folder in folders:
            folder_name = folder.name
            
            # 嘗試從資料夾名稱提取 gallery_id
            gallery_id = None
            
            # 方式 1: 純數字資料夾名
            if folder_name.isdigit():
                gallery_id = folder_name
            else:
                # 方式 2: 從 metadata.json 讀取
                metadata_path = folder / 'metadata.json'
                if metadata_path.exists():
                    try:
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            gallery_id = metadata.get('gallery_id') or metadata.get('nhentai_id')
                    except:
                        pass
            
            if gallery_id:
                # 檢查是否在 Eagle 中
                result = eagle.find_by_nhentai_id(str(gallery_id))
                if result:
                    can_delete.append((folder, gallery_id, result.get('title', '')[:30]))
                else:
                    not_in_eagle.append((folder, gallery_id))
            else:
                # 沒有 ID 的資料夾，用標題搜尋
                results = eagle.find_by_title(folder_name[:50])
                if results:
                    can_delete.append((folder, None, folder_name[:30]))
                else:
                    not_in_eagle.append((folder, None))
        
        if not can_delete:
            msg = f"✅ 沒有可清除的項目\n"
            msg += f"📁 imported 資料夾共 {len(folders)} 個項目\n"
            msg += f"⚠️ 其中 {len(not_in_eagle)} 個尚未導入 Eagle"
            await interaction.channel.send(msg)
            return
        
        # 顯示將要刪除的資料夾
        msg = f"🔍 發現 **{len(can_delete)}** 個已導入 Eagle 的項目可清除：\n\n"
        for folder, gid, title in can_delete[:10]:
            if gid:
                msg += f"• `#{gid}` {title}\n"
            else:
                msg += f"• {title}\n"
        if len(can_delete) > 10:
            msg += f"... 還有 {len(can_delete) - 10} 個\n"
        
        msg += f"\n📊 統計：已導入 {len(can_delete)} 個，未導入 {len(not_in_eagle)} 個"
        msg += "\n\n⚠️ **注意：只會刪除已確認導入 Eagle 的項目**"
        msg += "\n💡 未導入的項目會被保留"
        
        # 使用按鈕確認
        from bot.views import CleanupConfirmView
        view = CleanupConfirmView(
            can_delete=can_delete,
            not_in_eagle=not_in_eagle,
            user_id=interaction.user.id
        )
        
        await interaction.channel.send(msg, view=view)
        
    except Exception as e:
        logger.error(f"清除重複失敗: {e}")
        await interaction.followup.send(f"❌ 清除失敗: {e}")


# ==================== Eagle Library 搜尋指令 ====================

@bot.tree.command(name='search', description='搜尋本子 (Eagle Library + 下載資料夾)')
@app_commands.describe(
    query='搜尋關鍵字或 nhentai ID',
    source='搜尋來源 (預設: all)'
)
@app_commands.choices(source=[
    app_commands.Choice(name="全部", value="all"),
    app_commands.Choice(name="Eagle Library", value="eagle"),
    app_commands.Choice(name="下載資料夾", value="downloads"),
])
async def search_command(
    interaction: discord.Interaction, 
    query: str,
    source: str = "all"
):
    """搜尋本子 (支援雙來源)"""
    await interaction.response.defer()
    
    try:
        query = query.strip()
        results = []
        
        # 搜尋 Eagle Library
        if source in ['all', 'eagle']:
            try:
                from eagle_library import EagleLibrary
                eagle = EagleLibrary()
                
                if query.isdigit():
                    result = eagle.find_by_nhentai_id(query)
                    if result:
                        result['source'] = 'eagle'
                        results.append(result)
                else:
                    eagle_results = eagle.find_by_title(query)
                    for r in eagle_results:
                        r['source'] = 'eagle'
                        results.append(r)
            except Exception as e:
                logger.debug(f"Eagle 搜尋錯誤: {e}")
        
        # 搜尋 downloads 資料夾
        if source in ['all', 'downloads']:
            if query.isdigit():
                # 用 ID 搜尋
                for item in get_all_downloads_items():
                    if item.get('nhentai_id') == query:
                        # 避免重複（Eagle 已經有這個 ID）
                        if not any(r.get('nhentai_id') == query and r.get('source') == 'eagle' for r in results):
                            results.append(item)
            else:
                # 用關鍵字搜尋
                download_results = search_in_downloads(query)
                for item in download_results:
                    # 避免 ID 重複
                    item_id = item.get('nhentai_id')
                    if not any(r.get('nhentai_id') == item_id for r in results):
                        results.append(item)
        
        # 顯示搜尋類型
        if query.isdigit():
            search_type = f"ID `{query}`"
        else:
            search_type = f"`{query}`"
        
        source_label = {"all": "全部", "eagle": "Eagle", "downloads": "下載區"}.get(source, source)
        
        if not results:
            await interaction.followup.send(f"🔍 在 **{source_label}** 中找不到符合 {search_type} 的結果")
            return
        
        total = len(results)
        display_results = results[:10]
        
        # 判斷是否使用精簡模式 (超過 5 個結果)
        compact_mode = total > 5
        
        if compact_mode:
            # 精簡模式：使用分頁 embed
            from bot.views import SearchResultView
            
            # 傳入全部結果，View 會處理分頁
            view = SearchResultView(results, query, source, search_type="keyword")
            await interaction.followup.send(embed=view.get_embed(), view=view)
        else:
            # 詳細模式：類似 random 的顯示方式
            await interaction.followup.send(f"🔍 **{source_label}** 中找到 {total} 個結果 - {search_type}")
            
            for item in display_results:
                title = item.get('title', '未知')
                gallery_id = item.get('nhentai_id', '未知')
                web_url = item.get('web_url', '')
                tags = item.get('tags', [])
                folder_path = item.get('folder_path', '')
                item_source = item.get('source', 'eagle')
                
                # 解析 tags
                artists = [tag.replace('artist:', '') for tag in tags if isinstance(tag, str) and tag.startswith('artist:')]
                parodies = [tag.replace('parody:', '') for tag in tags if isinstance(tag, str) and tag.startswith('parody:')]
                
                # 計算檔案大小和頁數
                file_size_str = ""
                page_count = 0
                if folder_path:
                    try:
                        folder = Path(folder_path)
                        # 計算 PDF 檔案大小
                        pdf_files = list(folder.glob('*.pdf'))
                        if pdf_files:
                            pdf_size = pdf_files[0].stat().st_size
                            if pdf_size > 1024 * 1024:
                                file_size_str = f"{pdf_size / (1024*1024):.1f} MB"
                            else:
                                file_size_str = f"{pdf_size / 1024:.0f} KB"
                        
                        # 計算頁數 (圖片數量)
                        image_exts = ['*.jpg', '*.jpeg', '*.png', '*.webp', '*.gif']
                        for ext in image_exts:
                            page_count += len(list(folder.glob(ext)))
                    except Exception as e:
                        logger.debug(f"計算檔案資訊失敗: {e}")
                
                # 發送封面
                cover_sent = False
                if folder_path:
                    try:
                        folder = Path(folder_path)
                        for cover_name in ['cover.jpg', 'cover.png', 'cover.webp', 'thumbnail.png']:
                            cover_path = folder / cover_name
                            if cover_path.exists():
                                file = discord.File(str(cover_path), filename=cover_name)
                                await interaction.channel.send(file=file)
                                cover_sent = True
                                break
                        
                        if not cover_sent:
                            for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                                images = list(folder.glob(ext))
                                if images:
                                    images.sort(key=lambda x: x.name)
                                    file = discord.File(str(images[0]), filename=images[0].name)
                                    await interaction.channel.send(file=file)
                                    cover_sent = True
                                    break
                    except Exception as e:
                        logger.debug(f"封面發送失敗: {e}")
                
                # 發送資訊
                msg_lines = []
                source_emoji = "🦅" if item_source == 'eagle' else "📁"
                msg_lines.append(f"{source_emoji} **#{gallery_id}**")
                
                # 標題連結
                if item_source == 'eagle' and web_url:
                    msg_lines.append(f"📖 [{title}]({web_url})")
                elif item_source == 'downloads' and gallery_id:
                    pdf_url = f"{PDF_WEB_BASE_URL}/{quote(str(gallery_id))}/{quote(str(gallery_id))}.pdf"
                    msg_lines.append(f"📖 [{title}]({pdf_url})")
                else:
                    msg_lines.append(f"📖 **{title}**")
                
                if artists:
                    msg_lines.append(f"✍️ {', '.join(artists)}")
                if parodies:
                    msg_lines.append(f"🎬 {', '.join(parodies)}")
                
                # 加入檔案大小和頁數
                info_parts = []
                if page_count > 0:
                    info_parts.append(f"📄 {page_count} 頁")
                if file_size_str:
                    info_parts.append(f"💾 {file_size_str}")
                if info_parts:
                    msg_lines.append(" | ".join(info_parts))
                
                await interaction.channel.send("\n".join(msg_lines))
        
    except Exception as e:
        logger.error(f"搜尋失敗: {e}")
        await interaction.followup.send(f"❌ 搜尋失敗: {e}")


@bot.tree.command(name='read', description='取得本子的 PDF 連結 (支援 Eagle + 下載區)')
@app_commands.describe(nhentai_id='nhentai ID 或網址')
async def read_command(interaction: discord.Interaction, nhentai_id: str):
    """取得本子的 PDF 連結 (支援雙來源)"""
    await interaction.response.defer()
    
    # 清理輸入
    nhentai_id = nhentai_id.strip()
    if not nhentai_id.isdigit():
        # 嘗試從網址提取
        match = re.search(r'/g/(\d+)', nhentai_id)
        if match:
            nhentai_id = match.group(1)
        else:
            await interaction.followup.send("❌ 請提供有效的 nhentai ID 或網址")
            return
    
    try:
        # 使用雙來源查詢
        result = find_item_by_id(nhentai_id)
        
        if not result:
            await interaction.followup.send(
                f"🔍 找不到 ID `{nhentai_id}` 的本子\n"
                f"💡 可能尚未下載，請使用 `/dl {nhentai_id}` 下載"
            )
            return
        
        title = result.get('title', '未知')
        web_url = result.get('web_url', '')
        tags = result.get('tags', [])
        folder_path = result.get('folder_path', '')
        item_source = result.get('source', 'eagle')
        annotation = result.get('annotation', '')
        
        # 解析 tags
        artists = [tag.replace('artist:', '') for tag in tags if isinstance(tag, str) and tag.startswith('artist:')]
        parodies = [tag.replace('parody:', '') for tag in tags if isinstance(tag, str) and tag.startswith('parody:')]
        groups = [tag.replace('group:', '') for tag in tags if isinstance(tag, str) and tag.startswith('group:')]
        languages = [tag.replace('language:', '') for tag in tags if isinstance(tag, str) and tag.startswith('language:')]
        characters = [tag.replace('character:', '') for tag in tags if isinstance(tag, str) and tag.startswith('character:')]
        types = [tag.replace('type:', '') for tag in tags if isinstance(tag, str) and tag.startswith('type:')]
        other_tags = [tag for tag in tags if isinstance(tag, str) and not any(tag.startswith(prefix) for prefix in ['artist:', 'parody:', 'group:', 'language:', 'character:', 'type:'])]
        
        # 發送封面
        cover_sent = False
        if folder_path:
            try:
                folder = Path(folder_path)
                for cover_name in ['cover.jpg', 'cover.png', 'cover.webp', 'thumbnail.png']:
                    cover_path = folder / cover_name
                    if cover_path.exists():
                        file = discord.File(str(cover_path), filename=cover_name)
                        await interaction.followup.send(file=file)
                        cover_sent = True
                        break
                
                if not cover_sent:
                    for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                        images = list(folder.glob(ext))
                        if images:
                            images.sort(key=lambda x: x.name)
                            file = discord.File(str(images[0]), filename=images[0].name)
                            await interaction.followup.send(file=file)
                            cover_sent = True
                            break
            except Exception as e:
                logger.debug(f"封面發送失敗: {e}")
        
        # 建立資訊訊息
        msg_lines = []
        source_emoji = "🦅" if item_source == 'eagle' else "📁"
        
        msg_lines.append(f"{source_emoji} **#{nhentai_id}**")
        
        # 標題連結
        if item_source == 'eagle' and web_url:
            msg_lines.append(f"📖 [{title}]({web_url})")
        elif item_source == 'downloads':
            pdf_url = f"{PDF_WEB_BASE_URL}/{quote(nhentai_id)}/{quote(nhentai_id)}.pdf"
            msg_lines.append(f"📖 [{title}]({pdf_url})")
        else:
            msg_lines.append(f"📖 **{title}**")
        
        msg_lines.append("")
        
        # 來源
        msg_lines.append(f"📦 來源: {'Eagle Library' if item_source == 'eagle' else '下載資料夾'}")
        
        # 基本資訊
        if artists:
            msg_lines.append(f"✍️ 作者: {', '.join(artists)}")
        if groups:
            msg_lines.append(f"👥 社團: {', '.join(groups)}")
        if parodies:
            msg_lines.append(f"🎬 原作: {', '.join(parodies)}")
        if languages:
            msg_lines.append(f"🌐 語言: {', '.join(languages)}")
        if characters:
            msg_lines.append(f"👤 角色: {', '.join(characters)}")
        if types:
            msg_lines.append(f"📁 類型: {', '.join(types)}")
        
        # 使用者評論 (顯示全部)
        if annotation:
            comments = parse_annotation_comments(annotation)
            if comments:
                msg_lines.append("")
                msg_lines.append("💬 評論:")
                for c in comments:
                    msg_lines.append(f"  **{c['user']}**")
                    if c['content']:
                        msg_lines.append(f"  {c['content']}")
        
        # 標籤 (顯示全部)
        if other_tags:
            msg_lines.append("")
            msg_lines.append(f"🏷️ 標籤: {', '.join([f'`{tag}`' for tag in other_tags])}")
        
        # 發送資訊
        final_msg = "\n".join(msg_lines)
        if len(final_msg) > 1900:
            final_msg = final_msg[:1900] + "..."
        
        # 建立詳情頁互動視圖
        from bot.views import ReadDetailView
        view = ReadDetailView(
            gallery_id=nhentai_id,
            title=title,
            item_source=item_source,
            web_url=web_url,
            artists=artists,
            parodies=parodies,
            other_tags=other_tags
        )
        
        if cover_sent:
            await interaction.channel.send(final_msg, view=view)
        else:
            await interaction.followup.send(final_msg, view=view)
        
    except Exception as e:
        logger.error(f"讀取失敗: {e}")
        await interaction.followup.send(f"❌ 讀取失敗: {e}")


@bot.tree.command(name='eagle', description='顯示 Eagle Library 統計')
async def eagle_stats_command(interaction: discord.Interaction):
    """顯示 Eagle Library 統計"""
    await interaction.response.defer()
    
    try:
        from eagle_library import EagleLibrary
        eagle = EagleLibrary()
        
        stats = eagle.get_stats()
        
        embed = discord.Embed(
            title="🦅 Eagle Library 統計",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="📚 已匯入", value=f"`{stats['total_count']}` 本", inline=True)
        embed.add_field(name="🔢 有 ID", value=f"`{stats['with_nhentai_id']}` 本", inline=True)
        
        if stats.get('last_updated'):
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(stats['last_updated'].replace('Z', '+00:00'))
                embed.add_field(
                    name="🕐 最後更新",
                    value=dt.strftime("%Y-%m-%d %H:%M"),
                    inline=True
                )
            except:
                pass
        
        embed.set_footer(text="使用 /search <關鍵字> 搜尋 | /read <ID> 取得連結 | /reindex 重建索引")
        
        await interaction.followup.send(embed=embed)
        
    except ImportError:
        await interaction.followup.send("❌ Eagle Library 模組未安裝")
    except Exception as e:
        logger.error(f"統計失敗: {e}")
        await interaction.followup.send(f"❌ 統計失敗: {e}")


@bot.tree.command(name='reindex', description='重建 Eagle Library 索引')
async def reindex_command(interaction: discord.Interaction):
    """重建 Eagle Library 索引"""
    await interaction.response.defer()
    
    try:
        from eagle_library import EagleLibrary
        eagle = EagleLibrary()
        
        await interaction.followup.send("🔄 正在掃描 Eagle Library...")
        
        added = eagle.rebuild_index()
        stats = eagle.get_stats()
        
        if added > 0:
            await interaction.channel.send(f"✅ 索引重建完成！\n📥 新增 `{added}` 個項目\n📚 總計 `{stats['total_count']}` 本")
        else:
            await interaction.channel.send(f"✅ 索引已是最新！\n📚 總計 `{stats['total_count']}` 本")
        
    except ImportError:
        await interaction.followup.send("❌ Eagle Library 模組未安裝")
    except Exception as e:
        logger.error(f"重建索引失敗: {e}")
        await interaction.followup.send(f"❌ 重建索引失敗: {e}")


@bot.tree.command(name='help', description='顯示使用說明')
async def help_command(interaction: discord.Interaction):
    """顯示說明"""
    embed = discord.Embed(
        title="📖 HentaiFetcher 使用說明",
        description="自動下載漫畫並轉換為 PDF，生成 Eagle 相容 metadata",
        color=discord.Color.green()
    )
    
    # 檢查是否在專用頻道
    is_dedicated = (
        interaction.channel.name.lower() in [n.lower() for n in DEDICATED_CHANNEL_NAMES] or
        interaction.channel_id in DEDICATED_CHANNEL_IDS
    )
    
    if is_dedicated:
        embed.add_field(
            name="🎯 專用頻道模式（此頻道）",
            value="**所有指令都不需要前綴，直接輸入！**\n"
                  "━━━━━━━━━━━━━━━━━━\n"
                  "**📥 下載** - 直接貼網址或號碼：\n"
                  "```\n"
                  "421633\n"
                  "https://nhentai.net/g/607769/\n"
                  "```\n"
                  "**🧪 強制重新下載**：`test <號碼>`\n",
            inline=False
        )
    
    embed.add_field(
        name="📊 斜線指令",
        value="`/queue` - 查看佇列\n"
              "`/status` - Bot 狀態\n"
              "`/list` - 列出全部本子\n"
              "`/random [數量] [來源]` - 隨機抽\n"
              "`/fixcover` - 補充封面\n"
              "`/cleanup` - 清除已導入項目",
        inline=True
    )
    
    embed.add_field(
        name="🦅 Eagle + 下載區",
        value="`/search <關鍵字> [來源]` - 搜尋\n"
              "`/read <ID>` - 取得 PDF 連結\n"
              "`/eagle` - Library 統計\n"
              "`/reindex` - 重建索引\n"
              "━━━━━━━━━━━━\n"
              "🎮 **互動按鈕**: 搜尋/詳情頁支援點擊操作",
        inline=True
    )
    
    embed.add_field(
        name="ℹ️ 系統",
        value="`/ping` - 測試連線\n"
              "`/version` - 版本號\n"
              "`/sync` - 同步指令 (管理員)\n"
              "`/help` - 顯示此說明",
        inline=True
    )
    
    embed.add_field(
        name="📁 輸出結果",
        value="下載完成後會生成：\n"
              "```\n"
              "downloads/[Gallery_ID]/\n"
              "├── [Gallery_ID].pdf\n"
              "├── cover.jpg\n"
              "└── metadata.json\n"
              "```",
        inline=False
    )
    
    if is_dedicated:
        embed.set_footer(text="🎯 專用頻道：可直接貼號碼下載！")
    else:
        embed.set_footer(text="💡 使用斜線指令 / 開始")
    
    await interaction.response.send_message(embed=embed)


# ==================== 主程式入口 ====================

def main():
    """主程式入口"""
    # 取得 Discord Token
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        logger.error("錯誤: 未設定 DISCORD_TOKEN 環境變數")
        logger.error("請在 docker-compose.yml 中設定 DISCORD_TOKEN")
        sys.exit(1)
    
    try:
        logger.info("正在啟動 HentaiFetcher Bot...")
        bot.run(token)
    except discord.LoginFailure:
        logger.error("Discord 登入失敗: Token 無效")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Bot 執行錯誤: {e}")
        sys.exit(1)
    finally:
        # 停止工作執行緒
        if bot.worker:
            bot.worker.stop()


if __name__ == '__main__':
    main()
