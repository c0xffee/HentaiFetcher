"""
Tag Translator Service - 標籤翻譯服務
=====================================
功能：
- 英文 tag → 繁體中文翻譯
- 追蹤本地使用量和 nhentai 作品數
- 動態更新翻譯
"""

import json
import logging
import re
import aiohttp
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

logger = logging.getLogger('HentaiFetcher.tag_translator')

# 預設字典路徑
DEFAULT_DICT_PATH = Path(__file__).parent.parent / 'data' / 'tag_dictionary.json'


class TagTranslator:
    """
    Tag 翻譯服務
    
    字典結構:
    {
        "_meta": {...},
        "tags": {
            "lolicon": {
                "zh": "蘿莉控",
                "nhentai_count": 12345,
                "local_count": 5
            }
        }
    }
    """
    
    _instance: Optional['TagTranslator'] = None
    
    def __new__(cls, dict_path: Path = None):
        """單例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, dict_path: Path = None):
        """初始化翻譯器"""
        if self._initialized:
            return
            
        self.dict_path = dict_path or DEFAULT_DICT_PATH
        self.dictionary: Dict[str, Dict[str, Any]] = {}  # {tag: {zh, nhentai_count, local_count}}
        self.untranslated: set = set()
        self._load_dictionary()
        self._initialized = True
        
    def _load_dictionary(self) -> None:
        """載入翻譯字典"""
        try:
            if self.dict_path.exists():
                with open(self.dict_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    raw_tags = data.get('tags', {})
                    
                    # 轉換舊格式 (string) 到新格式 (dict)
                    for k, v in raw_tags.items():
                        k_lower = k.lower()
                        if isinstance(v, str):
                            # 舊格式: {"tag": "翻譯"}
                            self.dictionary[k_lower] = {
                                "zh": v,
                                "nhentai_count": 0,
                                "local_count": 0
                            }
                        elif isinstance(v, dict):
                            # 新格式: {"tag": {"zh": "翻譯", ...}}
                            self.dictionary[k_lower] = v
                    
                    logger.info(f"✅ 載入 tag 字典: {len(self.dictionary)} 個標籤")
            else:
                logger.warning(f"⚠️ 找不到 tag 字典: {self.dict_path}")
                self.dictionary = {}
        except Exception as e:
            logger.error(f"❌ 載入 tag 字典失敗: {e}")
            self.dictionary = {}
    
    def reload(self) -> int:
        """重新載入字典"""
        self.dictionary = {}
        self.untranslated = set()
        self._load_dictionary()
        return len(self.dictionary)
    
    def translate(self, tag: str, track_missing: bool = True) -> str:
        """翻譯單一 tag"""
        if not tag:
            return tag
            
        tag_lower = tag.lower().strip()
        tag_data = self.dictionary.get(tag_lower)
        
        if tag_data:
            zh = tag_data.get('zh', '')
            if zh:
                return zh
            else:
                if track_missing:
                    self.untranslated.add(tag_lower)
                return tag
        else:
            if track_missing and tag_lower:
                self.untranslated.add(tag_lower)
            return tag
    
    def translate_many(self, tags: List[str], track_missing: bool = True) -> List[str]:
        """批量翻譯 tags"""
        return [self.translate(tag, track_missing) for tag in tags]
    
    def get_untranslated(self) -> List[str]:
        """取得未翻譯清單 (zh 為空的)"""
        untranslated = []
        for tag, data in self.dictionary.items():
            if not data.get('zh'):
                untranslated.append(tag)
        return sorted(set(untranslated) | self.untranslated)
    
    def get_untranslated_count(self) -> int:
        """取得未翻譯數量"""
        return len(self.get_untranslated())
    
    def update_translation(self, en_tag: str, zh_tag: str) -> Tuple[bool, str]:
        """
        更新翻譯 (只能修改已存在的 tag)
        
        Returns:
            (成功與否, 訊息)
        """
        try:
            en_lower = en_tag.lower().strip()
            zh_clean = zh_tag.strip()
            
            if not en_lower:
                return False, "英文標籤不能為空"
            
            if en_lower not in self.dictionary:
                return False, f"標籤 `{en_tag}` 不存在於字典中"
            
            if not zh_clean:
                return False, "中文翻譯不能為空"
            
            old_zh = self.dictionary[en_lower].get('zh', '')
            self.dictionary[en_lower]['zh'] = zh_clean
            self.untranslated.discard(en_lower)
            
            self._save_dictionary()
            
            if old_zh:
                return True, f"已更新: `{old_zh}` → `{zh_clean}`"
            else:
                return True, f"已新增翻譯: `{zh_clean}`"
            
        except Exception as e:
            logger.error(f"❌ 更新翻譯失敗: {e}")
            return False, str(e)
    
    def increment_local_count(self, tags: List[str]) -> None:
        """增加本地使用計數"""
        for tag in tags:
            if not isinstance(tag, str):
                continue
            tag_lower = tag.lower().strip()
            if tag_lower in self.dictionary:
                self.dictionary[tag_lower]['local_count'] = self.dictionary[tag_lower].get('local_count', 0) + 1
    
    def register_tag(self, tag: str, nhentai_count: int = 0) -> bool:
        """
        註冊新 tag (下載時自動呼叫)
        """
        tag_lower = tag.lower().strip()
        if not tag_lower:
            return False
        
        if tag_lower not in self.dictionary:
            self.dictionary[tag_lower] = {
                "zh": "",
                "nhentai_count": nhentai_count,
                "local_count": 1
            }
            return True
        else:
            # 已存在，增加 local_count
            self.dictionary[tag_lower]['local_count'] = self.dictionary[tag_lower].get('local_count', 0) + 1
            # 如果 nhentai_count 是 0 且傳入有值，更新
            if nhentai_count > 0 and self.dictionary[tag_lower].get('nhentai_count', 0) == 0:
                self.dictionary[tag_lower]['nhentai_count'] = nhentai_count
            return False
    
    def get_tag_info(self, tag: str) -> Optional[Dict]:
        """取得 tag 資訊"""
        tag_lower = tag.lower().strip()
        return self.dictionary.get(tag_lower)
    
    def get_all_tags_sorted(self, sort_by: str = "local") -> List[Tuple[str, Dict]]:
        """
        取得所有 tag 並排序
        
        Args:
            sort_by: "local" (本地數量), "nhentai" (nhentai 數量), "alpha" (字母)
        """
        items = list(self.dictionary.items())
        
        if sort_by == "local":
            items.sort(key=lambda x: x[1].get('local_count', 0), reverse=True)
        elif sort_by == "nhentai":
            items.sort(key=lambda x: x[1].get('nhentai_count', 0), reverse=True)
        else:
            items.sort(key=lambda x: x[0])
        
        return items
    
    def _save_dictionary(self) -> bool:
        """儲存字典到檔案"""
        try:
            self.dict_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "_meta": {
                    "version": "2.0.0",
                    "updated": datetime.now().strftime('%Y-%m-%d'),
                    "total_tags": len(self.dictionary)
                },
                "tags": dict(sorted(self.dictionary.items()))
            }
            
            with open(self.dict_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"✅ 儲存 tag 字典: {len(self.dictionary)} 個標籤")
            return True
            
        except Exception as e:
            logger.error(f"❌ 儲存 tag 字典失敗: {e}")
            return False
    
    def save(self) -> bool:
        """公開的儲存方法"""
        return self._save_dictionary()
    
    def get_stats(self) -> Dict:
        """取得統計資訊"""
        translated = sum(1 for d in self.dictionary.values() if d.get('zh'))
        return {
            'total_tags': len(self.dictionary),
            'translated': translated,
            'untranslated': len(self.dictionary) - translated,
            'dict_path': str(self.dict_path)
        }


async def fetch_nhentai_tag_count(tag: str) -> int:
    """
    從 nhentai 抓取 tag 的作品數量
    
    Args:
        tag: 英文 tag (如 "lolicon")
    
    Returns:
        作品數量，失敗則返回 0
    """
    try:
        url = f"https://nhentai.net/tag/{tag.replace(' ', '-')}/"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return 0
                
                html = await response.text()
                
                # 解析 <span class="count">(12345)</span>
                match = re.search(r'<span class="count">\(?([\d,]+)\)?</span>', html)
                if match:
                    count_str = match.group(1).replace(',', '')
                    return int(count_str)
                
                return 0
                
    except Exception as e:
        logger.debug(f"抓取 nhentai tag 數量失敗 ({tag}): {e}")
        return 0


def get_translator() -> TagTranslator:
    """取得全域 TagTranslator 實例"""
    return TagTranslator()
