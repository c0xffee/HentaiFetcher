#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher nhentai API Service
=================================
與 nhentai.net API 互動的服務
"""

import requests
from pathlib import Path
from typing import Dict, Any, Tuple

from core.config import logger


# HTTP Headers
NHENTAI_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


def verify_nhentai_url(gallery_id: str) -> Tuple[bool, str]:
    """
    驗證 nhentai gallery 是否存在且可訪問
    
    Args:
        gallery_id: Gallery ID
    
    Returns:
        (是否有效, 標題或錯誤訊息)
    """
    try:
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=NHENTAI_HEADERS, timeout=15)
        
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


def get_nhentai_page_count(gallery_id: str) -> Tuple[int, str, str]:
    """
    從 nhentai API 獲取頁數、標題和 media_id
    
    Args:
        gallery_id: Gallery ID
    
    Returns:
        (頁數, 標題, media_id) - 失敗時頁數為 0
    """
    try:
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=NHENTAI_HEADERS, timeout=15)
        
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
    
    # 獲取收藏數
    try:
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=NHENTAI_HEADERS, timeout=30)
        if response.status_code == 200:
            data = response.json()
            result['favorites'] = data.get('num_favorites', 0)
            logger.info(f"獲取收藏數: {result['favorites']}")
    except Exception as e:
        logger.warning(f"獲取收藏數失敗: {e}")
    
    # 獲取評論
    try:
        comments_url = f"https://nhentai.net/api/gallery/{gallery_id}/comments"
        response = requests.get(comments_url, headers=NHENTAI_HEADERS, timeout=30)
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
    try:
        # 獲取 gallery 資訊
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=NHENTAI_HEADERS, timeout=30)
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
                response = requests.get(cover_url, headers=NHENTAI_HEADERS, timeout=30)
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
    try:
        # 獲取 gallery 資訊
        api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
        response = requests.get(api_url, headers=NHENTAI_HEADERS, timeout=30)
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
                response = requests.get(page_url, headers=NHENTAI_HEADERS, timeout=30)
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
