#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher Index Service
===========================
索引管理、搜尋與查詢服務
"""

import re
import json
import time
import secrets
import unicodedata
from typing import Dict, Any, List, Optional

from core.config import logger, DOWNLOAD_DIR, REINDEX_COOLDOWN


# 快速 reindex 標記 - 用於避免頻繁重複索引
_last_reindex_time: float = 0


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


def check_already_downloaded(gallery_id: str, do_reindex: bool = False) -> tuple:
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


def get_random_gallery_id(source_filter: str = "all") -> Optional[str]:
    """
    快速獲取一個隨機的 gallery ID (優化版，不載入完整資訊)
    
    Args:
        source_filter: 來源篩選 (all/eagle/downloads)
    
    Returns:
        隨機選中的 gallery ID，或 None
    """
    all_ids = []
    
    # 從 Eagle 索引快速獲取 ID 列表
    if source_filter in ("all", "eagle"):
        try:
            from eagle_library import EagleLibrary
            eagle = EagleLibrary()
            index = eagle._load_index()
            for entry in index.get("imports", {}).values():
                nid = entry.get("nhentaiId")
                if nid:
                    all_ids.append(nid)
        except Exception as e:
            logger.debug(f"Eagle 索引讀取錯誤: {e}")
    
    # 從 downloads 快速獲取 ID 列表
    if source_filter in ("all", "downloads"):
        try:
            if DOWNLOAD_DIR.exists():
                for folder in DOWNLOAD_DIR.iterdir():
                    if folder.is_dir():
                        # 直接用資料夾名稱作為 ID (通常就是 gallery ID)
                        folder_name = folder.name
                        if folder_name.isdigit():
                            if folder_name not in all_ids:
                                all_ids.append(folder_name)
        except Exception as e:
            logger.debug(f"Downloads 目錄讀取錯誤: {e}")
    
    if not all_ids:
        return None
    
    return secrets.choice(all_ids)


def search_in_downloads(query: str) -> List[Dict[str, Any]]:
    """
    在 downloads 資料夾中搜尋本子
    
    Args:
        query: 搜尋關鍵字（支援 ID、標題、作者、原作等）
    
    Returns:
        符合條件的本子列表
    """
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
