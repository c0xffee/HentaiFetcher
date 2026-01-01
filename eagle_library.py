"""
Eagle Library 查詢工具
供 Discord Bot 查詢 Eagle 中的 PDF 檔案並生成 Web URL

使用方式:
    from eagle_library import EagleLibrary
    
    eagle = EagleLibrary()
    
    # 用 nhentai ID 查詢
    result = eagle.find_by_nhentai_id("486715")
    if result:
        print(result['web_url'])
    
    # 用 Eagle Item ID 查詢
    result = eagle.find_by_eagle_id("MJVZNHLIT4O3D")
"""

import os
import json
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, List, Any


class EagleLibrary:
    def __init__(
        self,
        library_images_path: str = "//192.168.10.2/docker/Eagle/nHentai.library/images",
        web_base_url: str = "http://192.168.10.2:8889",
        index_file_path: str = "//192.168.10.2/docker/HentaiFetcher/imports-index.json"
    ):
        """
        初始化 Eagle Library 查詢工具
        
        Args:
            library_images_path: Eagle Library images 資料夾的 UNC 路徑
            web_base_url: Web Station 的基礎 URL (對應 images 資料夾)
            index_file_path: imports-index.json 的路徑
        """
        self.library_images_path = Path(library_images_path)
        self.web_base_url = web_base_url.rstrip('/')
        self.index_file_path = Path(index_file_path)
        self._index_cache: Optional[Dict] = None
        self._index_mtime: float = 0
    
    def _load_index(self) -> Dict:
        """載入索引檔案 (帶快取)"""
        try:
            mtime = self.index_file_path.stat().st_mtime
            if self._index_cache is None or mtime > self._index_mtime:
                with open(self.index_file_path, 'r', encoding='utf-8') as f:
                    self._index_cache = json.load(f)
                self._index_mtime = mtime
            return self._index_cache
        except Exception as e:
            print(f"載入索引失敗: {e}")
            return {"imports": {}}
    
    def _find_pdf_in_folder(self, folder_path: Path) -> Optional[str]:
        """在指定資料夾中找到 PDF 檔案"""
        try:
            if not folder_path.exists():
                return None
            
            for file in folder_path.iterdir():
                if file.suffix.lower() == '.pdf':
                    return file.name
            return None
        except Exception as e:
            print(f"搜尋資料夾失敗: {e}")
            return None
    
    def _build_web_url(self, eagle_item_id: str, pdf_filename: str) -> str:
        """組合 Web URL"""
        folder_name = f"{eagle_item_id}.info"
        encoded_folder = urllib.parse.quote(folder_name, safe='')
        encoded_file = urllib.parse.quote(pdf_filename, safe='')
        return f"{self.web_base_url}/{encoded_folder}/{encoded_file}"
    
    def find_by_eagle_id(self, eagle_item_id: str) -> Optional[Dict[str, Any]]:
        """
        用 Eagle Item ID 查詢 PDF
        
        Args:
            eagle_item_id: Eagle 的 Item ID (如 "MJVZNHLIT4O3D")
        
        Returns:
            包含 web_url, pdf_filename, folder_path 的字典，或 None
        """
        folder_path = self.library_images_path / f"{eagle_item_id}.info"
        pdf_filename = self._find_pdf_in_folder(folder_path)
        
        if not pdf_filename:
            return None
        
        return {
            "eagle_item_id": eagle_item_id,
            "pdf_filename": pdf_filename,
            "folder_path": str(folder_path),
            "web_url": self._build_web_url(eagle_item_id, pdf_filename)
        }
    
    def find_by_nhentai_id(self, nhentai_id: str) -> Optional[Dict[str, Any]]:
        """
        用 nhentai ID 查詢 PDF
        
        Args:
            nhentai_id: nhentai 的 Gallery ID (如 "486715")
        
        Returns:
            包含 web_url, pdf_filename, title 等資訊的字典，或 None
        """
        index = self._load_index()
        
        # 在索引中搜尋對應的 nhentai ID
        for folder_name, entry in index.get("imports", {}).items():
            if entry.get("nhentaiId") == str(nhentai_id):
                eagle_item_id = entry.get("eagleItemId")
                if eagle_item_id:
                    result = self.find_by_eagle_id(eagle_item_id)
                    if result:
                        # 附加索引中的額外資訊
                        result["title"] = entry.get("title", folder_name)
                        result["nhentai_id"] = nhentai_id
                        result["nhentai_url"] = entry.get("nhentaiUrl")
                        result["tags"] = entry.get("tags", [])
                        return result
        return None
    
    def find_by_title(self, keyword: str) -> List[Dict[str, Any]]:
        """
        用標題關鍵字搜尋 PDF
        
        Args:
            keyword: 搜尋關鍵字
        
        Returns:
            符合條件的結果列表
        """
        index = self._load_index()
        results = []
        
        keyword_lower = keyword.lower()
        for folder_name, entry in index.get("imports", {}).items():
            title = entry.get("title", folder_name)
            if keyword_lower in title.lower() or keyword_lower in folder_name.lower():
                eagle_item_id = entry.get("eagleItemId")
                if eagle_item_id:
                    result = self.find_by_eagle_id(eagle_item_id)
                    if result:
                        result["title"] = title
                        result["nhentai_id"] = entry.get("nhentaiId")
                        result["nhentai_url"] = entry.get("nhentaiUrl")
                        result["tags"] = entry.get("tags", [])
                        results.append(result)
        
        return results
    
    def list_all(self) -> List[Dict[str, Any]]:
        """列出所有已匯入的項目"""
        index = self._load_index()
        results = []
        
        for folder_name, entry in index.get("imports", {}).items():
            results.append({
                "folder_name": folder_name,
                "eagle_item_id": entry.get("eagleItemId"),
                "nhentai_id": entry.get("nhentaiId"),
                "title": entry.get("title", folder_name),
                "nhentai_url": entry.get("nhentaiUrl"),
                "imported_at": entry.get("importedAt")
            })
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """取得統計資訊"""
        index = self._load_index()
        imports = index.get("imports", {})
        
        return {
            "total_count": len(imports),
            "last_updated": index.get("lastUpdated"),
            "with_nhentai_id": sum(1 for e in imports.values() if e.get("nhentaiId")),
        }


# 快速使用的單例
_default_eagle: Optional[EagleLibrary] = None

def get_eagle_library() -> EagleLibrary:
    """取得預設的 EagleLibrary 實例"""
    global _default_eagle
    if _default_eagle is None:
        _default_eagle = EagleLibrary()
    return _default_eagle


# 便捷函數
def find_pdf_url(nhentai_id: str) -> Optional[str]:
    """快速查詢 nhentai ID 對應的 Web URL"""
    result = get_eagle_library().find_by_nhentai_id(nhentai_id)
    return result["web_url"] if result else None


if __name__ == "__main__":
    # 測試
    eagle = EagleLibrary()
    
    print("=== 統計 ===")
    print(eagle.get_stats())
    
    print("\n=== 用 nhentai ID 查詢 ===")
    result = eagle.find_by_nhentai_id("486715")
    if result:
        print(f"標題: {result['title']}")
        print(f"Web URL: {result['web_url']}")
    else:
        print("找不到")
    
    print("\n=== 用關鍵字搜尋 ===")
    results = eagle.find_by_title("ギャル")
    for r in results[:3]:
        print(f"- {r['title']}")
        print(f"  URL: {r['web_url']}")
