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
        library_images_path: str = None,
        web_base_url: str = None,
        index_file_path: str = None
    ):
        """
        初始化 Eagle Library 查詢工具
        
        Args:
            library_images_path: Eagle Library images 資料夾路徑
            web_base_url: Web Station 的基礎 URL (對應 images 資料夾)
            index_file_path: imports-index.json 的路徑
        
        路徑優先順序: 參數 > 環境變數 > 預設值
        """
        import os
        
        # 判斷是否在 Docker 容器中 (檢查 /app 目錄)
        is_docker = os.path.exists('/app/run.py')
        
        # 預設值根據環境不同
        if is_docker:
            default_library_path = "/app/eagle-library"
            default_index_path = "/app/imports-index.json"
        else:
            default_library_path = "//192.168.0.32/docker/Eagle/nHentai.library/images"
            default_index_path = "//192.168.0.32/docker/HentaiFetcher/imports-index.json"
        
        default_web_url = "http://192.168.0.32:8889"
        
        # 使用優先順序: 參數 > 環境變數 > 預設值
        self.library_images_path = Path(
            library_images_path or 
            os.environ.get('EAGLE_LIBRARY_PATH', default_library_path)
        )
        self.web_base_url = (
            web_base_url or 
            os.environ.get('EAGLE_WEB_URL', default_web_url)
        ).rstrip('/')
        self.index_file_path = Path(
            index_file_path or 
            os.environ.get('IMPORTS_INDEX_PATH', default_index_path)
        )
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
                        
                        # 讀取 Eagle metadata.json 獲取 annotation (包含收藏數)
                        try:
                            metadata_path = self.library_images_path / f"{eagle_item_id}.info" / "metadata.json"
                            if metadata_path.exists():
                                with open(metadata_path, 'r', encoding='utf-8') as f:
                                    eagle_meta = json.load(f)
                                    result["annotation"] = eagle_meta.get("annotation", "")
                        except Exception:
                            pass
                        
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
                        
                        # 讀取 Eagle metadata.json 獲取 annotation (包含收藏數)
                        try:
                            metadata_path = self.library_images_path / f"{eagle_item_id}.info" / "metadata.json"
                            if metadata_path.exists():
                                with open(metadata_path, 'r', encoding='utf-8') as f:
                                    eagle_meta = json.load(f)
                                    result["annotation"] = eagle_meta.get("annotation", "")
                        except Exception:
                            result["annotation"] = ""
                        
                        results.append(result)
        
        return results
    
    def find_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        """
        用標籤搜尋 PDF
        
        Args:
            tag: 標籤名稱 (完整匹配，如 "artist:sky" 或 "gyaru")
        
        Returns:
            符合條件的結果列表
        """
        index = self._load_index()
        results = []
        
        tag_lower = tag.lower()
        for folder_name, entry in index.get("imports", {}).items():
            tags = entry.get("tags", [])
            # 檢查是否有匹配的標籤 (不區分大小寫)
            if any(tag_lower == t.lower() for t in tags):
                eagle_item_id = entry.get("eagleItemId")
                if eagle_item_id:
                    result = self.find_by_eagle_id(eagle_item_id)
                    if result:
                        result["title"] = entry.get("title", folder_name)
                        result["nhentai_id"] = entry.get("nhentaiId")
                        result["nhentai_url"] = entry.get("nhentaiUrl")
                        result["tags"] = tags
                        
                        # 讀取 Eagle metadata.json 獲取 annotation (包含收藏數)
                        try:
                            metadata_path = self.library_images_path / f"{eagle_item_id}.info" / "metadata.json"
                            if metadata_path.exists():
                                with open(metadata_path, 'r', encoding='utf-8') as f:
                                    eagle_meta = json.load(f)
                                    result["annotation"] = eagle_meta.get("annotation", "")
                        except Exception:
                            result["annotation"] = ""
                        
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
    
    def get_all_items(self) -> List[Dict[str, Any]]:
        """
        獲取所有已匯入的項目（含完整資訊）
        
        Returns:
            包含完整資訊的項目列表 (包括 folder_path, web_url, tags 等)
        """
        index = self._load_index()
        imports = index.get("imports", {})
        results = []
        
        for folder_name, entry in imports.items():
            eagle_item_id = entry.get("eagleItemId")
            
            if eagle_item_id:
                # 取得完整資訊
                result = self.find_by_eagle_id(eagle_item_id)
                if result:
                    result["folder_name"] = folder_name
                    result["title"] = entry.get("title", folder_name)
                    result["nhentai_id"] = entry.get("nhentaiId")
                    result["nhentai_url"] = entry.get("nhentaiUrl")
                    result["tags"] = entry.get("tags", [])
                    result["annotation"] = entry.get("annotation", "")
                    result["imported_at"] = entry.get("importedAt")
                    results.append(result)
        
        return results
    
    def get_random(self, count: int = 1) -> List[Dict[str, Any]]:
        """
        隨機取得已匯入的項目
        
        Args:
            count: 要取得的數量
        
        Returns:
            隨機選取的項目列表 (含完整資訊)
        """
        import secrets
        
        index = self._load_index()
        imports = index.get("imports", {})
        
        if not imports:
            return []
        
        # 限制數量
        count = min(count, len(imports))
        
        # 使用 secrets 模組進行加密安全的隨機選取（更加隨機）
        keys_list = list(imports.keys())
        selected_indices = set()
        while len(selected_indices) < count:
            idx = secrets.randbelow(len(keys_list))
            selected_indices.add(idx)
        
        selected_keys = [keys_list[i] for i in selected_indices]
        results = []
        
        for folder_name in selected_keys:
            entry = imports[folder_name]
            eagle_item_id = entry.get("eagleItemId")
            
            if eagle_item_id:
                # 取得 PDF 完整資訊
                result = self.find_by_eagle_id(eagle_item_id)
                if result:
                    result["folder_name"] = folder_name
                    result["title"] = entry.get("title", folder_name)
                    result["nhentai_id"] = entry.get("nhentaiId")
                    result["nhentai_url"] = entry.get("nhentaiUrl")
                    result["tags"] = entry.get("tags", [])
                    result["imported_at"] = entry.get("importedAt")
                    results.append(result)
        
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
    
    def rebuild_index(self) -> int:
        """
        從 Eagle Library 重建索引
        掃描所有 .info 資料夾，讀取 metadata.json 建立完整索引
        
        Returns:
            新增的項目數量
        """
        import re
        
        if not self.library_images_path.exists():
            print(f"Eagle Library 路徑不存在: {self.library_images_path}")
            return 0
        
        # 載入現有索引
        index = self._load_index()
        existing_ids = {e.get("eagleItemId") for e in index.get("imports", {}).values()}
        
        added = 0
        
        # 掃描所有 .info 資料夾
        for folder in self.library_images_path.iterdir():
            if not folder.is_dir() or not folder.name.endswith('.info'):
                continue
            
            eagle_item_id = folder.name.replace('.info', '')
            
            # 跳過已存在的
            if eagle_item_id in existing_ids:
                continue
            
            # 讀取 Eagle 的 metadata.json
            eagle_metadata_path = folder / "metadata.json"
            if not eagle_metadata_path.exists():
                continue
            
            try:
                with open(eagle_metadata_path, 'r', encoding='utf-8') as f:
                    eagle_meta = json.load(f)
                
                # 從 Eagle metadata 提取資訊
                name = eagle_meta.get("name", "")
                website = eagle_meta.get("url", "")
                tags = eagle_meta.get("tags", [])
                annotation = eagle_meta.get("annotation", "")
                
                # 從 website 提取 nhentai ID
                nhentai_id = None
                if website:
                    match = re.search(r'nhentai\.net/g/(\d+)', website)
                    if match:
                        nhentai_id = match.group(1)
                
                # 從 annotation 提取 nhentai ID (備用)
                if not nhentai_id and annotation:
                    match = re.search(r'📔 ID: (\d+)', annotation)
                    if match:
                        nhentai_id = match.group(1)
                
                # 使用 name 作為 key
                folder_key = name if name else eagle_item_id
                
                # 加入索引
                index["imports"][folder_key] = {
                    "eagleItemId": eagle_item_id,
                    "nhentaiId": nhentai_id,
                    "nhentaiUrl": website if 'nhentai' in website else None,
                    "title": name,
                    "tags": tags,
                    "importedAt": eagle_meta.get("mtime", "")
                }
                
                added += 1
                print(f"新增: {folder_key} (ID: {nhentai_id or 'N/A'})")
                
            except Exception as e:
                print(f"讀取失敗 {folder.name}: {e}")
        
        # 儲存索引
        if added > 0:
            index["lastUpdated"] = __import__('datetime').datetime.now().isoformat() + 'Z'
            with open(self.index_file_path, 'w', encoding='utf-8') as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
            
            # 清除快取
            self._index_cache = None
            print(f"\n索引已更新，新增 {added} 個項目")
        
        return added


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


def rebuild_index() -> int:
    """重建索引的便捷函數"""
    return get_eagle_library().rebuild_index()


if __name__ == "__main__":
    import sys
    
    eagle = EagleLibrary()
    
    # 如果帶 --rebuild 參數，重建索引
    if len(sys.argv) > 1 and sys.argv[1] == '--rebuild':
        print("=== 重建索引 ===")
        added = eagle.rebuild_index()
        print(f"完成，新增 {added} 個項目")
        print()
    
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
