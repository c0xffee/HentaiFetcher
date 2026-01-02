"""
HentaiFetcher Discord UI Views
==============================
持久化互動元件模組

所有 View 都支援：
- 持久化 (Bot 重啟後仍可運作)
- 5 分鐘超時自動禁用
- custom_id 格式: {action}:{data}
"""

from .base import BaseView, TIMEOUT_SECONDS
from .search_view import SearchResultView
from .read_view import ReadDetailView
from .random_view import RandomResultView
from .download_view import DownloadCompleteView

__all__ = [
    'BaseView',
    'TIMEOUT_SECONDS',
    'SearchResultView',
    'ReadDetailView', 
    'RandomResultView',
    'DownloadCompleteView',
]
