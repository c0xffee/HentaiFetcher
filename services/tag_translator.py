"""
Tag Translator Service - 標籤翻譯服務
=====================================
功能：
- 英文 tag → 繁體中文翻譯
- 單一翻譯 / 批量翻譯
- 追蹤未翻譯 tag
- 動態新增翻譯
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger('HentaiFetcher.tag_translator')

# 預設字典路徑
DEFAULT_DICT_PATH = Path(__file__).parent.parent / 'data' / 'tag_dictionary.json'


class TagTranslator:
    """
    Tag 翻譯服務
    
    使用方式:
        translator = TagTranslator()
        zh_tag = translator.translate("lolicon")  # → "蘿莉控"
        zh_tags = translator.translate_many(["swimsuit", "bikini"])  # → ["泳裝", "比基尼"]
    """
    
    _instance: Optional['TagTranslator'] = None
    
    def __new__(cls, dict_path: Path = None):
        """單例模式 - 確保全域共用同一個 translator 實例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, dict_path: Path = None):
        """初始化翻譯器"""
        if self._initialized:
            return
            
        self.dict_path = dict_path or DEFAULT_DICT_PATH
        self.dictionary: Dict[str, str] = {}
        self.untranslated: set = set()  # 追蹤未翻譯的 tag
        self._load_dictionary()
        self._initialized = True
        
    def _load_dictionary(self) -> None:
        """載入翻譯字典"""
        try:
            if self.dict_path.exists():
                with open(self.dict_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.dictionary = data.get('tags', {})
                    # 全部轉小寫以便比對
                    self.dictionary = {k.lower(): v for k, v in self.dictionary.items()}
                    logger.info(f"✅ 載入 tag 字典: {len(self.dictionary)} 個翻譯")
            else:
                logger.warning(f"⚠️ 找不到 tag 字典: {self.dict_path}")
                self.dictionary = {}
        except Exception as e:
            logger.error(f"❌ 載入 tag 字典失敗: {e}")
            self.dictionary = {}
    
    def reload(self) -> int:
        """重新載入字典，回傳載入的翻譯數量"""
        self.dictionary = {}
        self.untranslated = set()
        self._load_dictionary()
        return len(self.dictionary)
    
    def translate(self, tag: str, track_missing: bool = True) -> str:
        """
        翻譯單一 tag
        
        Args:
            tag: 英文 tag
            track_missing: 是否追蹤未翻譯的 tag
            
        Returns:
            繁中翻譯，若無則回傳原 tag
        """
        if not tag:
            return tag
            
        tag_lower = tag.lower().strip()
        translated = self.dictionary.get(tag_lower)
        
        if translated:
            return translated
        else:
            if track_missing and tag_lower:
                self.untranslated.add(tag_lower)
            return tag  # 回傳原 tag
    
    def translate_many(self, tags: List[str], track_missing: bool = True) -> List[str]:
        """
        批量翻譯 tags
        
        Args:
            tags: 英文 tag 列表
            track_missing: 是否追蹤未翻譯的 tag
            
        Returns:
            翻譯後的 tag 列表
        """
        return [self.translate(tag, track_missing) for tag in tags]
    
    def translate_with_original(self, tags: List[str]) -> List[Tuple[str, str]]:
        """
        批量翻譯並保留原文
        
        Returns:
            [(原文, 翻譯), ...] 的列表
        """
        return [(tag, self.translate(tag)) for tag in tags]
    
    def get_untranslated(self) -> List[str]:
        """取得尚未翻譯的 tag 清單 (已排序)"""
        return sorted(self.untranslated)
    
    def get_untranslated_count(self) -> int:
        """取得未翻譯 tag 數量"""
        return len(self.untranslated)
    
    def clear_untranslated(self) -> None:
        """清空未翻譯追蹤"""
        self.untranslated = set()
    
    def add_translation(self, en_tag: str, zh_tag: str) -> bool:
        """
        新增翻譯到字典
        
        Args:
            en_tag: 英文 tag
            zh_tag: 繁體中文翻譯
            
        Returns:
            是否成功儲存
        """
        try:
            en_lower = en_tag.lower().strip()
            zh_clean = zh_tag.strip()
            
            if not en_lower or not zh_clean:
                return False
            
            # 更新記憶體字典
            self.dictionary[en_lower] = zh_clean
            
            # 從未翻譯清單移除
            self.untranslated.discard(en_lower)
            
            # 儲存到檔案
            return self._save_dictionary()
            
        except Exception as e:
            logger.error(f"❌ 新增翻譯失敗: {e}")
            return False
    
    def remove_translation(self, en_tag: str) -> bool:
        """
        移除翻譯
        
        Args:
            en_tag: 要移除的英文 tag
            
        Returns:
            是否成功移除
        """
        try:
            en_lower = en_tag.lower().strip()
            
            if en_lower in self.dictionary:
                del self.dictionary[en_lower]
                return self._save_dictionary()
            return False
            
        except Exception as e:
            logger.error(f"❌ 移除翻譯失敗: {e}")
            return False
    
    def _save_dictionary(self) -> bool:
        """儲存字典到檔案"""
        try:
            # 確保目錄存在
            self.dict_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 讀取現有結構 (保留 _meta)
            data = {"_meta": {}, "tags": {}}
            if self.dict_path.exists():
                with open(self.dict_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            
            # 更新 meta
            data['_meta']['updated'] = datetime.now().strftime('%Y-%m-%d')
            data['_meta']['total_tags'] = len(self.dictionary)
            
            # 更新 tags (按字母排序)
            data['tags'] = dict(sorted(self.dictionary.items()))
            
            # 寫入檔案
            with open(self.dict_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 儲存 tag 字典: {len(self.dictionary)} 個翻譯")
            return True
            
        except Exception as e:
            logger.error(f"❌ 儲存 tag 字典失敗: {e}")
            return False
    
    def search(self, keyword: str) -> List[Tuple[str, str]]:
        """
        搜尋字典
        
        Args:
            keyword: 搜尋關鍵字 (英文或中文)
            
        Returns:
            [(英文tag, 中文翻譯), ...] 的列表
        """
        keyword_lower = keyword.lower().strip()
        results = []
        
        for en, zh in self.dictionary.items():
            if keyword_lower in en.lower() or keyword_lower in zh:
                results.append((en, zh))
        
        return sorted(results, key=lambda x: x[0])
    
    def get_stats(self) -> Dict:
        """取得統計資訊"""
        return {
            'total_translations': len(self.dictionary),
            'untranslated_count': len(self.untranslated),
            'dict_path': str(self.dict_path)
        }


# 全域單例 (方便其他模組使用)
def get_translator() -> TagTranslator:
    """取得全域 TagTranslator 實例"""
    return TagTranslator()
