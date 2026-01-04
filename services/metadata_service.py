#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher Metadata Service
==============================
Metadata 解析與生成服務
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from core.config import logger
from utils.helpers import generate_eagle_id, format_comments_for_annotation
from services.tag_translator import get_translator


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
        
        # ===== 自動註冊新 tag 到翻譯字典 =====
        _register_new_tags(result['tags'])
        
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


def _register_new_tags(tags: List[str]) -> int:
    """
    自動註冊新 tag 到翻譯字典
    
    - 有前綴的 tag (artist:, parody:, group: 等) 會被忽略
    - 新 tag 會被加入字典
    - 已有的 tag 會增加 local_count
    
    Args:
        tags: tag 列表
        
    Returns:
        新增的 tag 數量
    """
    try:
        translator = get_translator()
        new_count = 0
        
        # 需要跳過的前綴
        skip_prefixes = ['artist:', 'parody:', 'group:', 'language:', 'character:', 'type:', 'category:']
        
        for tag in tags:
            if not isinstance(tag, str):
                continue
            
            # 跳過有前綴的 tag
            if any(tag.startswith(prefix) for prefix in skip_prefixes):
                continue
            
            tag_lower = tag.lower().strip()
            if not tag_lower:
                continue
            
            # 使用新的 register_tag 方法
            is_new = translator.register_tag(tag_lower)
            if is_new:
                new_count += 1
        
        # 儲存字典
        translator.save()
        
        if new_count > 0:
            logger.debug(f"自動註冊 {new_count} 個新 tag 到翻譯字典")
        
        return new_count
        
    except Exception as e:
        logger.warning(f"註冊新 tag 失敗: {e}")
        return 0


async def register_new_tags_async(tags: List[str]) -> int:
    """
    非同步註冊新 tag (含抓取 nhentai 數量)
    
    Args:
        tags: tag 列表
        
    Returns:
        新增的 tag 數量
    """
    from services.tag_translator import fetch_nhentai_tag_count
    
    try:
        translator = get_translator()
        new_count = 0
        
        skip_prefixes = ['artist:', 'parody:', 'group:', 'language:', 'character:', 'type:', 'category:']
        
        for tag in tags:
            if not isinstance(tag, str):
                continue
            
            if any(tag.startswith(prefix) for prefix in skip_prefixes):
                continue
            
            tag_lower = tag.lower().strip()
            if not tag_lower:
                continue
            
            # 檢查是否為新 tag
            if tag_lower not in translator.dictionary:
                # 抓取 nhentai 數量
                nhentai_count = await fetch_nhentai_tag_count(tag_lower)
                translator.register_tag(tag_lower, nhentai_count)
                new_count += 1
                logger.debug(f"新 tag: {tag_lower} (nhentai: {nhentai_count})")
            else:
                # 已存在，只增加 local_count
                translator.register_tag(tag_lower)
        
        translator.save()
        
        if new_count > 0:
            logger.info(f"自動註冊 {new_count} 個新 tag 到翻譯字典")
        
        return new_count
        
    except Exception as e:
        logger.warning(f"非同步註冊新 tag 失敗: {e}")
        return 0
