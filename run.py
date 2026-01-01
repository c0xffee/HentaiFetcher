#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher - Discord Bot 自動化漫畫下載器
==============================================
版本: 2.0.1 - 2024-12-30 多行輸入修復版
功能：
1. Discord Bot 監聯 !dl 指令（支援多個網址或號碼）
2. 使用 gallery-dl 下載圖片與 metadata
3. 使用 img2pdf 轉換為無損 PDF
4. 生成 Eagle 相容的 metadata.json
5. 自動清理原始圖片檔案
"""

# 版本號 - 用來確認容器是否更新
VERSION = "2.8.0"

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

import discord
from discord.ext import commands

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

# 下載佇列 - 結構: (url, channel_id, status_message_id)
download_queue: Queue = Queue()

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
    
    def __init__(self, url: str, total_pages: int = 0, message_callback=None):
        """
        初始化下載處理器
        
        Args:
            url: 要下載的網址
            total_pages: 預期總頁數（用於進度計算）
            message_callback: 狀態更新回調函式
        """
        self.url = url
        self.total_pages = total_pages
        self.message_callback = message_callback
        self.temp_path: Optional[Path] = None
        self.output_path: Optional[Path] = None
        self.last_error: str = ""
        self.download_complete = False  # 下載是否完成
        self.pdf_progress = 0  # PDF 轉換進度 (0-100)
        self.pdf_converting = False  # 是否正在轉換 PDF
        
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
                cmd = [
                    sys.executable,
                    '-m', 'gallery_dl',
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
            self.pdf_progress = 75
            
            # 第一張圖片作為基底，其餘 append
            first_image = resized_images[0]
            rest_images = resized_images[1:] if len(resized_images) > 1 else []
            
            first_image.save(
                output_pdf,
                "PDF",
                save_all=True,
                append_images=rest_images,
                resolution=100.0
            )
            
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
            # 步驟 1: 下載
            logger.info(f"開始下載: {self.url}")
            print(f"[PROCESS] 開始下載: {self.url}", flush=True)
            if not self.download_with_gallery_dl():
                error_detail = self.last_error if self.last_error else "未知原因"
                elapsed = time.time() - start_time
                return False, f"❌ 下載失敗\n🔗 {self.url}\n⏱️ 耗時: {elapsed:.1f}s\n\n{error_detail}"
            
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
            
            if not title:
                # 嘗試從 URL 提取 ID 作為標題
                match = re.search(r'/g/(\d+)', self.url)
                if match:
                    title = f"Gallery_{match.group(1)}"
                else:
                    title = f"Download_{int(time.time())}"
            
            safe_title = sanitize_filename(title)
            logger.info(f"使用標題: {safe_title}")
            
            # 建立輸出資料夾
            self.output_path = DOWNLOAD_DIR / safe_title
            
            # 如果資料夾已存在，使用時間戳命名避免覆蓋
            if self.output_path.exists():
                self.output_path = DOWNLOAD_DIR / f"{safe_title}_{int(time.time())}"
                logger.info(f"資料夾已存在，使用新資料夾 {self.output_path}")
            
            self.output_path.mkdir(parents=True, exist_ok=True)
            
            # 步驟 3: 轉換為 PDF
            pdf_path = self.output_path / f"{safe_title}.pdf"
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
            pdf_filename = f"{safe_title}.pdf"
            pdf_web_url = f"{PDF_WEB_BASE_URL}/{quote(folder_name)}/{quote(pdf_filename)}"
            
            # 標題嵌入連結，讓使用者可以直接點擊觀看 PDF
            return True, f"✅ 完成: [{safe_title}]({pdf_web_url})\n📄 {page_count}頁 ⏱️ {elapsed_str}\n📁 {output_path_str}"
            
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
                
                # 支援格式: (url, channel_id), (url, channel_id, status_msg_id), 或 (url, channel_id, status_msg_id, test_mode)
                if len(task) == 4:
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
                match = re.search(r'/g/(\d+)', url)
                if match:
                    gallery_id = match.group(1)
                    pages, title, media_id = get_nhentai_page_count(gallery_id)
                    if pages > 0:
                        # 發送開始下載訊息（包含頁數和預估時間），並返回訊息 ID
                        future = asyncio.run_coroutine_threadsafe(
                            self.send_start_message(channel_id, gallery_id, pages, title, media_id),
                            self.bot.loop
                        )
                        start_msg_id = future.result(timeout=10)
                
                # 創建下載處理器
                processor = DownloadProcessor(url, total_pages=pages)
                
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
                
                # 停止進度監控
                progress_stop_event.set()
                
                # 更新開始下載訊息（顯示最終狀態）
                if start_msg_id:
                    asyncio.run_coroutine_threadsafe(
                        self.update_final_progress(channel_id, start_msg_id, success, pages, title, media_id),
                        self.bot.loop
                    )
                
                # 發送結果到 Discord
                asyncio.run_coroutine_threadsafe(
                    self.send_result(channel_id, message),
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
                                    success: bool, total: int, title: str, media_id: str = ""):
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
                await message.edit(content=f"✅ 下載完成\n📖 {title}\n{progress_bar}\n({total}/{total})")
                await message.add_reaction('✅')
            else:
                await message.add_reaction('❌')
            
        except Exception as e:
            logger.error(f"更新最終進度失敗: {e}")
    
    async def send_start_message(self, channel_id: int, gallery_id: str, pages: int, title: str, media_id: str = "") -> int:
        """
        發送開始下載訊息（包含頁數和預估時間）
        
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
                
                # 發送進度訊息
                msg = await channel.send(
                    f"🔄 開始下載 **#{gallery_id}**\n"
                    f"📖 {title}\n"
                    f"{progress_bar}\n"
                    f"(0/{pages}) ⏱️ 預估: {est_str}"
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
    
    async def on_ready(self):
        """Bot 連線成功時觸發"""
        logger.info(f'Bot 已登入: {self.user.name} (ID: {self.user.id})')
        logger.info(f'已連接到 {len(self.guilds)} 個伺服器')
        
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
        if is_dedicated_channel and not content.startswith('!'):
            # 在專用頻道中，任何看起來像 URL 或數字的訊息都嘗試處理
            await self.handle_direct_download(message, content)
            return
        
        # ===== 傳統模式：處理 !dl 指令（支援多行）=====
        if content.startswith('!dl'):
            # 強制輸出 debug 訊息
            print(f"[DEBUG] !dl 指令偵測到!", flush=True)
            print(f"[DEBUG] 完整內容長度: {len(content)}", flush=True)
            print(f"[DEBUG] 完整內容: {repr(content)}", flush=True)
            logger.info(f"收到 !dl 指令，完整內容: {repr(content)}")
            
            # 提取 !dl 之後的所有內容（包括換行）
            urls_text = content[3:].strip()  # 移除 "!dl" 前綴
            
            print(f"[DEBUG] 解析文字: {repr(urls_text)}", flush=True)
            logger.info(f"解析文字: {repr(urls_text)}")
            
            if not urls_text:
                await message.channel.send(
                    "📖 **!dl 使用方式**\n"
                    "```\n"
                    "!dl 421633\n"
                    "!dl 421633 607769 613358\n"
                    "!dl https://nhentai.net/g/421633/\n"
                    "```\n"
                    "也可以直接貼多行：\n"
                    "```\n"
                    "!dl 421633\n"
                    "607769\n"
                    "613358\n"
                    "```"
                )
                return
            
            # 解析所有網址
            parsed_urls = parse_input_to_urls(urls_text)
            
            print(f"[DEBUG] 解析結果數量: {len(parsed_urls)}", flush=True)
            print(f"[DEBUG] 解析結果: {parsed_urls}", flush=True)
            logger.info(f"解析結果: {parsed_urls}")
            
            if not parsed_urls:
                await message.channel.send("⚠️ 無法解析輸入。請提供有效的網址或 nhentai 號碼。")
                return
            
            # 發送狀態訊息（簡化版，只顯示號碼）
            queue_size = download_queue.qsize() + len(parsed_urls)
            
            # 提取所有 gallery ID
            gallery_ids = []
            for url in parsed_urls:
                match = re.search(r'/g/(\d+)', url)
                if match:
                    gallery_ids.append(match.group(1))
            
            if len(parsed_urls) == 1 and gallery_ids:
                await message.channel.send(f"📥 **#{gallery_ids[0]}** 已加入佇列\n📊 佇列: {queue_size}")
            elif len(gallery_ids) <= 15:
                id_list = ", ".join([f"`{gid}`" for gid in gallery_ids])
                await message.channel.send(f"📥 **{len(gallery_ids)}** 個已加入佇列\n🔢 {id_list}\n📊 佇列: {queue_size}")
            else:
                await message.channel.send(f"📥 **{len(parsed_urls)}** 個已加入佇列\n📊 佇列: {queue_size}")
            
            # 加入佇列（不再傳遞 status_msg_id，因為 loading emoji 改在開始下載時顯示）
            for url in parsed_urls:
                download_queue.put((url, message.channel.id, None))
            
            logger.info(f"新增 {len(parsed_urls)} 個下載任務 (來自: {message.author})")
            return
        
        # ===== 處理 !test 指令（強制重新下載，跳過重複檢查）=====
        if content.startswith('!test'):
            print(f"[DEBUG] !test 指令偵測到!", flush=True)
            logger.info(f"收到 !test 指令，完整內容: {repr(content)}")
            
            # 提取 !test 之後的所有內容
            urls_text = content[5:].strip()  # 移除 "!test" 前綴
            
            if not urls_text:
                await message.channel.send(
                    "🧪 **!test 使用方式（強制重新下載）**\n"
                    "```\n"
                    "!test 421633\n"
                    "!test https://nhentai.net/g/421633/\n"
                    "```\n"
                    "⚠️ 此模式會跳過重複檢查，即使已下載過也會重新下載"
                )
                return
            
            # 解析所有網址
            parsed_urls = parse_input_to_urls(urls_text)
            
            if not parsed_urls:
                await message.channel.send("⚠️ 無法解析輸入。請提供有效的網址或 nhentai 號碼。")
                return
            
            # 發送狀態訊息
            queue_size = download_queue.qsize() + len(parsed_urls)
            
            # 提取所有 gallery ID
            gallery_ids = []
            for url in parsed_urls:
                match = re.search(r'/g/(\d+)', url)
                if match:
                    gallery_ids.append(match.group(1))
            
            if len(parsed_urls) == 1 and gallery_ids:
                await message.channel.send(f"🧪 **#{gallery_ids[0]}** 已加入佇列（Test 模式）\n📊 佇列: {queue_size}")
            else:
                id_list = ", ".join([f"`{gid}`" for gid in gallery_ids[:10]])
                await message.channel.send(f"🧪 **{len(gallery_ids)}** 個已加入佇列（Test 模式）\n🔢 {id_list}\n📊 佇列: {queue_size}")
            
            # 加入佇列（第4個參數 True 表示 test_mode）
            for url in parsed_urls:
                download_queue.put((url, message.channel.id, None, True))
            
            logger.info(f"新增 {len(parsed_urls)} 個 TEST 下載任務 (來自: {message.author})")
            return
        
        # 處理其他指令
        await self.process_commands(message)
    
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
            else:
                id_list = ", ".join([f"`{gid}`" for gid in gallery_ids[:10]])
                await message.channel.send(f"🧪 **{len(gallery_ids)}** 個已加入佇列（Test 模式）\n🔢 {id_list}\n📊 佇列: {queue_size}")
            
            for url in test_urls:
                download_queue.put((url, message.channel.id, None, True))
            
            logger.info(f"[專用頻道] 新增 {len(test_urls)} 個 TEST 下載任務 (來自: {message.author})")
            return
        
        # 解析輸入
        parsed_urls = parse_input_to_urls(content)
        
        if not parsed_urls:
            # 如果無法解析，靜默忽略（不發送錯誤訊息，避免打擾）
            # 但如果內容看起來像是想要下載（純數字或包含 nhentai），給予提示
            if re.search(r'\d{4,7}', content) or 'nhentai' in content.lower():
                await message.channel.send(f"⚠️ 無法解析: `{content[:50]}`\n請確認格式正確（例如: `607769` 或 `https://nhentai.net/g/607769/`）")
            return
        
        # 驗證並加入佇列
        valid_urls = []
        invalid_urls = []
        
        # 添加 reaction 表示處理中
        try:
            await message.add_reaction('⏳')
        except:
            pass
        
        for url in parsed_urls:
            # 提取 gallery ID
            match = re.search(r'/g/(\d+)', url)
            if match:
                gallery_id = match.group(1)
                
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
        
        # 處理無效的 URL
        if invalid_urls:
            error_list = "\n".join([f"• `{id}`: {reason}" for id, reason in invalid_urls[:5]])
            await message.channel.send(f"❌ 以下無法下載:\n{error_list}")
        
        # 加入有效的 URL
        if valid_urls:
            queue_size = download_queue.qsize() + len(valid_urls)
            
            # 發送簡化的狀態訊息（只顯示號碼）
            if len(valid_urls) == 1:
                _, gallery_id, _ = valid_urls[0]
                await message.channel.send(f"📥 **#{gallery_id}** 已加入佇列\n📊 佇列: {queue_size}")
            else:
                id_list = ", ".join([f"`{gid}`" for _, gid, _ in valid_urls[:10]])
                await message.channel.send(f"📥 **{len(valid_urls)}** 個已加入佇列\n🔢 {id_list}\n📊 佇列: {queue_size}")
            
            # 添加成功 reaction 到原始訊息
            try:
                await message.add_reaction('✅')
            except:
                pass
            
            # 加入佇列（不傳遞 status_msg_id，loading emoji 改在開始下載時顯示）
            for url, gallery_id, title in valid_urls:
                download_queue.put((url, message.channel.id, None))
            
            logger.info(f"[專用頻道] 新增 {len(valid_urls)} 個下載任務 (來自: {message.author})")
    
    async def on_command_error(self, ctx, error):
        """全域錯誤處理"""
        if isinstance(error, commands.CommandNotFound):
            return  # 忽略未知指令
        
        logger.error(f"指令錯誤: {error}")
        await ctx.send(f"⚠️ 發生錯誤: {str(error)}")


# 建立 Bot 實例
bot = HentaiFetcherBot()


# ==================== 傳統指令 ====================

@bot.command(name='queue', aliases=['q'])
async def queue_command(ctx):
    """查看下載佇列：!queue 或 !q"""
    size = download_queue.qsize()
    await ctx.send(f"📊 佇列中等待任務: {size}")


@bot.command(name='ping')
async def ping_command(ctx):
    """測試連線：!ping"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! 延遲: {latency}ms")


@bot.command(name='version', aliases=['v', 'ver'])
async def version_command(ctx):
    """顯示版本：!version 或 !v"""
    await ctx.send(f"📦 HentaiFetcher 版本: **{VERSION}**")


@bot.command(name='status')
async def status_command(ctx):
    """顯示狀態：!status"""
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
    
    embed.set_footer(text="使用 !dl <號碼或網址> 開始下載")
    
    await ctx.send(embed=embed)


@bot.command(name='list', aliases=['ls', 'library'])
async def list_command(ctx):
    """列出所有已下載的本子：!list"""
    try:
        from urllib.parse import quote
        
        if not DOWNLOAD_DIR.exists():
            await ctx.send("📂 下載資料夾不存在")
            return
        
        # 獲取所有子資料夾
        folders = [f for f in DOWNLOAD_DIR.iterdir() if f.is_dir()]
        
        if not folders:
            await ctx.send("📂 目前沒有任何下載")
            return
        
        # 構建純文字訊息（分批發送以避免 2000 字元限制）
        items = []
        
        for folder in folders:
            folder_name = folder.name
            
            # 嘗試從 metadata.json 獲取 gallery_id
            metadata_path = folder / "metadata.json"
            gallery_id = ""
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
                except:
                    pass
            
            items.append((gallery_id, folder_name))
        
        # 按號碼排序（從小到大）
        items.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)
        
        # 構建輸出
        msg_lines = []
        for gallery_id, folder_name in items:
            # 格式：`#號碼` 書名（不要連結）
            if gallery_id:
                msg_lines.append(f"`#{gallery_id}` {folder_name}")
            else:
                msg_lines.append(f"{folder_name}")
        
        # 分批發送（每批最多 1800 字元）
        header = f"📚 **已下載的本子** (共 {len(folders)} 本)\n"
        await ctx.send(header)
        
        current_batch = []
        current_length = 0
        
        for line in msg_lines:
            line_length = len(line) + 1  # +1 for newline
            if current_length + line_length > 1800:
                # 發送當前批次
                await ctx.send("\n".join(current_batch))
                current_batch = [line]
                current_length = line_length
            else:
                current_batch.append(line)
                current_length += line_length
        
        # 發送最後一批
        if current_batch:
            await ctx.send("\n".join(current_batch))
        
    except Exception as e:
        logger.error(f"列出下載失敗: {e}")
        await ctx.send(f"❌ 列出失敗: {e}")


@bot.command(name='random', aliases=['rand', 'r'])
async def random_command(ctx, count: int = 1):
    """隨機顯示本子：!random [數量]"""
    try:
        from urllib.parse import quote
        import random
        
        if not DOWNLOAD_DIR.exists():
            await ctx.send("📂 下載資料夾不存在")
            return
        
        # 獲取所有子資料夾
        folders = [f for f in DOWNLOAD_DIR.iterdir() if f.is_dir()]
        
        if not folders:
            await ctx.send("📂 目前沒有任何下載")
            return
        
        # 限制數量
        count = max(1, min(count, 5))  # 1-5 本
        count = min(count, len(folders))  # 不超過總數
        
        # 隨機選擇
        selected = random.sample(folders, count)
        
        for folder in selected:
            folder_name = folder.name
            
            # 讀取 metadata
            metadata_path = folder / "metadata.json"
            metadata = {}
            if metadata_path.exists():
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                except:
                    pass
            
            # 獲取基本資料
            gallery_id = metadata.get('gallery_id', '')
            # 如果沒有 gallery_id，從 URL 提取
            if not gallery_id:
                url = metadata.get('url', '')
                match = re.search(r'/g/(\d+)', url)
                if match:
                    gallery_id = match.group(1)
            if not gallery_id:
                gallery_id = '未知'
            
            # 從 metadata 獲取標題
            title = metadata.get('name', metadata.get('title', folder_name))
            
            # 從 annotation 解析信息
            annotation = metadata.get('annotation', '')
            title_japanese = ''
            pages = '未知'
            
            # 解析 annotation
            if annotation:
                # 提取英文標題
                title_match = re.search(r'📖 英文標題: (.+?)(?:\n|$)', annotation)
                if title_match:
                    title_japanese = title_match.group(1).strip()
                
                # 提取頁數
                pages_match = re.search(r'📄 頁數: (\d+)', annotation)
                if pages_match:
                    pages = pages_match.group(1)
            
            # 從 tags 解析作者（tags 是字串列表）
            tags = metadata.get('tags', [])
            if not isinstance(tags, list):
                tags = []
            artists = [tag.replace('artist:', '') for tag in tags if isinstance(tag, str) and tag.startswith('artist:')]
            parodies = [tag.replace('parody:', '') for tag in tags if isinstance(tag, str) and tag.startswith('parody:')]
            groups = [tag.replace('group:', '') for tag in tags if isinstance(tag, str) and tag.startswith('group:')]
            languages = [tag.replace('language:', '') for tag in tags if isinstance(tag, str) and tag.startswith('language:')]
            
            # 其他 tags（不包含類型前綴的）
            other_tags = [tag for tag in tags if isinstance(tag, str) and not any(tag.startswith(prefix) for prefix in ['artist:', 'parody:', 'group:', 'language:', 'type:'])]
            
            # 查找 PDF 和封面
            pdf_files = list(folder.glob("*.pdf"))
            
            # 查找封面 - 先找圖片檔案
            cover_files = []
            # 搜索所有可能的封面檔案
            for pattern in ["cover.*", "000.*", "001.*", "01.*", "1.*", "2.*", "3.*"]:
                found = list(folder.glob(pattern))
                if found:
                    # 過濾出圖片檔案
                    cover_files = [f for f in found if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp', '.gif']]
                    if cover_files:
                        break
            
            # 如果沒有找到圖片，嘗試從所有圖片中找第一張
            if not cover_files:
                all_images = []
                for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                    all_images.extend(folder.glob(f"*{ext}"))
                if all_images:
                    # 按檔名排序取第一張
                    all_images.sort(key=lambda x: x.name)
                    cover_files = [all_images[0]]
            
            # 先發送封面圖片（單獨一則訊息）
            if cover_files:
                cover_file = cover_files[0]
                try:
                    file = discord.File(str(cover_file), filename=cover_file.name)
                    await ctx.send(file=file)
                    logger.info(f"成功發送封面: {cover_file.name}")
                except Exception as e:
                    logger.error(f"發送封面失敗 ({cover_file}): {e}")
            else:
                # 沒有封面時發送提示
                logger.warning(f"找不到封面圖片: {folder_name}")
            
            # 構建純文字資料訊息
            msg_lines = []
            
            # PDF 連結標題 - 使用分隔線美化
            msg_lines.append("━━━━━━━━━━━━━━━━━━")
            if pdf_files:
                pdf_name = pdf_files[0].name
                pdf_url = f"{PDF_WEB_BASE_URL}/{quote(folder_name)}/{quote(pdf_name)}"
                # 連結文字簡潔顯示，URL 隱藏在 markdown 連結中
                msg_lines.append(f"📖 **#{gallery_id}** │ [📥 點擊閱讀 PDF](<{pdf_url}>)")
            else:
                msg_lines.append(f"📖 **#{gallery_id}**")
            msg_lines.append("━━━━━━━━━━━━━━━━━━\n")
            
            # 標題
            if title:
                msg_lines.append(f"**{title}**")
            if title_japanese and title_japanese != title:
                msg_lines.append(f"_{title_japanese}_\n")
            else:
                msg_lines.append("")
            
            # 基本信息 - 分行顯示更清楚
            msg_lines.append("**📊 基本資料**")
            if pages != '未知':
                msg_lines.append(f"├ 📄 頁數: **{pages}**")
            if artists:
                msg_lines.append(f"├ ✍️ 作者: {', '.join(artists[:3])}")
            if groups:
                msg_lines.append(f"├ 👥 社團: {', '.join(groups[:2])}")
            if parodies:
                msg_lines.append(f"├ 🎬 原作: {', '.join(parodies[:3])}")
            if languages:
                msg_lines.append(f"└ 🌐 語言: {', '.join(languages)}")
            
            # Tags
            if other_tags:
                msg_lines.append(f"\n**🏷️ 標籤**")
                tags_text = ", ".join([f"`{tag}`" for tag in other_tags[:12]])
                if len(other_tags) > 12:
                    tags_text += f" `+{len(other_tags)-12}`"
                msg_lines.append(tags_text)
            
            msg_lines.append("\n━━━━━━━━━━━━━━━━━━")
            
            # 發送資料訊息
            final_msg = "\n".join(msg_lines)
            if len(final_msg) > 1900:
                final_msg = final_msg[:1900] + "..."
            await ctx.send(final_msg)
        
    except Exception as e:
        logger.error(f"隨機顯示失敗: {e}")
        await ctx.send(f"❌ 隨機顯示失敗: {e}")


@bot.command(name='fixcover', aliases=['fc', 'addcover'])
async def fixcover_command(ctx):
    """為已有的本子補充封面（從 nhentai 下載或使用第一張圖片）：!fixcover"""
    try:
        if not DOWNLOAD_DIR.exists():
            await ctx.send("📂 下載資料夾不存在")
            return
        
        await ctx.send("🔍 開始掃描並補充封面...")
        
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
        await ctx.send(msg)
        
    except Exception as e:
        logger.error(f"補充封面失敗: {e}")
        await ctx.send(f"❌ 補充封面失敗: {e}")


@bot.command(name='cleanup', aliases=['clean', 'dedup'])
async def cleanup_command(ctx):
    """清除重複的資料夾（有時間戳後綴的）：!cleanup"""
    try:
        if not DOWNLOAD_DIR.exists():
            await ctx.send("📂 下載資料夾不存在")
            return
        
        # 找出有時間戳後綴的資料夾（格式：標題_時間戳）
        import re
        timestamp_pattern = re.compile(r'^(.+)_(\d{10})$')  # 10 位數時間戳
        
        folders = [f for f in DOWNLOAD_DIR.iterdir() if f.is_dir()]
        duplicates = []
        
        for folder in folders:
            match = timestamp_pattern.match(folder.name)
            if match:
                original_name = match.group(1)
                original_path = DOWNLOAD_DIR / original_name
                
                # 如果原始資料夾也存在，這個就是重複的
                if original_path.exists() and original_path.is_dir():
                    duplicates.append(folder)
        
        if not duplicates:
            await ctx.send("✅ 沒有發現重複的資料夾")
            return
        
        # 顯示將要刪除的資料夾
        msg = f"🔍 發現 {len(duplicates)} 個重複資料夾：\n"
        for dup in duplicates[:10]:
            msg += f"• `{dup.name}`\n"
        if len(duplicates) > 10:
            msg += f"... 還有 {len(duplicates) - 10} 個\n"
        msg += "\n⚠️ 確定要刪除嗎？回覆 `確認` 或 `yes` 來執行刪除"
        
        await ctx.send(msg)
        
        # 等待確認
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['確認', 'yes', 'y']
        
        try:
            confirm_msg = await bot.wait_for('message', timeout=30.0, check=check)
        except:
            await ctx.send("⏰ 超時，取消操作")
            return
        
        # 執行刪除
        deleted = 0
        for dup in duplicates:
            try:
                shutil.rmtree(dup)
                deleted += 1
                logger.info(f"已刪除重複資料夾: {dup.name}")
            except Exception as e:
                logger.error(f"刪除失敗 {dup.name}: {e}")
        
        await ctx.send(f"✅ 已刪除 {deleted}/{len(duplicates)} 個重複資料夾")
        
    except Exception as e:
        logger.error(f"清除重複失敗: {e}")
        await ctx.send(f"❌ 清除失敗: {e}")


@bot.command(name='help', aliases=['h'])
async def help_command(ctx):
    """顯示說明：!help"""
    embed = discord.Embed(
        title="📖 HentaiFetcher 使用說明",
        description="自動下載漫畫並轉換為 PDF，生成 Eagle 相容 metadata",
        color=discord.Color.green()
    )
    
    # 檢查是否在專用頻道
    is_dedicated = (
        ctx.channel.name.lower() in [n.lower() for n in DEDICATED_CHANNEL_NAMES] or
        ctx.channel.id in DEDICATED_CHANNEL_IDS
    )
    
    if is_dedicated:
        embed.add_field(
            name="🎯 專用頻道模式（此頻道）",
            value="**所有指令都不需要 `!` 前綴！**\n"
                  "━━━━━━━━━━━━━━━━━━\n"
                  "**📥 下載** - 直接貼網址或號碼：\n"
                  "```\n"
                  "421633\n"
                  "https://nhentai.net/g/607769/\n"
                  "421633 607769 613358\n"
                  "```\n"
                  "**🧪 強制重新下載**：`test <號碼>`\n"
                  "**📊 其他指令：**\n"
                  "`queue` `q` - 查看佇列\n"
                  "`status` - Bot 狀態\n"
                  "`list` `ls` - 列出已下載\n"
                  "`random` `r [n]` - 隨機顯示\n"
                  "`fixcover` `fc` - 補充封面\n"
                  "`cleanup` `clean` - 清除重複\n"
                  "`ping` - 測試連線\n"
                  "`version` `v` - 版本號\n"
                  "`help` `h` - 顯示此說明",
            inline=False
        )
    else:
        embed.add_field(
            name="📥 !dl <網址或號碼>",
            value="**下載漫畫**\n"
                  "```\n"
                  "!dl 421633\n"
                  "!dl 421633 607769 613358\n"
                  "!dl https://nhentai.net/g/421633/\n"
                  "```\n"
                  "支援多行輸入：\n"
                  "```\n"
                  "!dl 421633\n"
                  "607769\n"
                  "https://nhentai.net/g/613358/\n"
                  "```",
            inline=False
        )
        
        embed.add_field(
            name="🧪 !test <網址或號碼>",
            value="強制重新下載（跳過重複檢查）",
            inline=True
        )
        
        embed.add_field(
            name="📊 !queue 或 !q",
            value="查看下載佇列任務數",
            inline=True
        )
        
        embed.add_field(
            name="📈 !status",
            value="顯示 Bot 狀態",
            inline=True
        )
        
        embed.add_field(
            name="📚 !list 或 !ls",
            value="列出已下載項目",
            inline=True
        )
        
        embed.add_field(
            name="🎲 !random [n]",
            value="隨機顯示 n 本",
            inline=True
        )
        
        embed.add_field(
            name="🖼️ !fixcover",
            value="補充封面圖片",
            inline=True
        )
        
        embed.add_field(
            name="🧹 !cleanup 或 !clean",
            value="清除重複資料夾",
            inline=True
        )
        
        embed.add_field(
            name="🏓 !ping",
            value="測試 Bot 連線",
            inline=True
        )
        
        embed.add_field(
            name="📦 !version 或 !v",
            value="顯示 Bot 版本號",
            inline=True
        )
    
    embed.add_field(
        name="📁 輸出結果",
        value="下載完成後會生成：\n"
              "```\n"
              "downloads/[漫畫標題]/\n"
              "├── [漫畫標題].pdf\n"
              "└── metadata.json (Eagle 用)\n"
              "```",
        inline=False
    )
    
    if is_dedicated:
        embed.set_footer(text="🎯 專用頻道：所有指令都不需要 ! 前綴！")
    else:
        embed.set_footer(text="💡 可一次貼多個號碼或網址，用空白/逗號/換行分隔")
    
    await ctx.send(embed=embed)


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
