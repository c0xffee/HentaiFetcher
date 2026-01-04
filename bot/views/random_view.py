"""
Random Result View - 隨機結果互動視圖
=====================================
v3.3.9 簡化版：
- 移除「詳細資訊」按鈕（/random 已直接輸出詳細格式）
- 移除「下載此本」按鈕（本子已在庫中）
- 開啟 PDF 按鈕
- 隨機一本按鈕（使用統一詳細模板）
"""

import discord
from discord import ui
from typing import List, Optional, Dict, Any
from urllib.parse import quote
from pathlib import Path
import logging
import secrets

from .base import BaseView, TIMEOUT_SECONDS
from .helpers import build_safe_pdf_url, show_item_detail, send_cover_image, DISCORD_URL_MAX_LENGTH

logger = logging.getLogger('HentaiFetcher.views')

PDF_WEB_BASE_URL = "https://com1c.c0xffee.com"


class RandomResultView(BaseView):
    """隨機結果互動視圖 (v3.3.9 簡化版)"""
    
    def __init__(
        self,
        gallery_id: str,
        title: str,
        item_source: str = "eagle",
        web_url: str = "",
        artists: List[str] = None,
        source_filter: str = "all",
        *,
        timeout: float = TIMEOUT_SECONDS
    ):
        super().__init__(timeout=timeout)
        
        self.gallery_id = gallery_id
        self.title = title
        self.item_source = item_source
        self.web_url = web_url
        self.artists = artists or []
        self.source_filter = source_filter
        
        # Row 0: 連結按鈕
        # 開啟 PDF (Link Button) - 檢查 URL 長度
        pdf_url = build_safe_pdf_url(gallery_id, item_source, web_url)
        if pdf_url:
            pdf_button = ui.Button(
                label="📄 開啟 PDF",
                style=discord.ButtonStyle.link,
                url=pdf_url,
                row=0
            )
            self.add_item(pdf_button)
        
        # nhentai 連結 (這個 URL 永遠很短)
        nhentai_url = f"https://nhentai.net/g/{gallery_id}/"
        nhentai_button = ui.Button(
            label="🔗 nhentai",
            style=discord.ButtonStyle.link,
            url=nhentai_url,
            row=0
        )
        self.add_item(nhentai_button)
    
    # v3.3.9: 移除「詳細資訊」按鈕 - /random 已直接輸出詳細格式
    # v3.3.9: 移除「下載此本」按鈕 - 本子已在庫中無需再下載
    
    @ui.button(label="🎲 隨機一本", style=discord.ButtonStyle.primary, custom_id="random_again", row=1)
    async def random_again_button(self, interaction: discord.Interaction, button: ui.Button):
        """隨機一本 - 使用統一詳細模板 (優化版)"""
        await interaction.response.defer()
        
        try:
            from services.index_service import get_random_gallery_id
            
            # 使用優化的隨機 ID 獲取函數
            gallery_id = get_random_gallery_id(self.source_filter)
            
            if not gallery_id:
                await interaction.followup.send("❌ 沒有可抽選的作品", ephemeral=True)
                return
            
            # 使用統一詳細模板顯示 (show_cover=True 會發送封面，並附帶 ReadDetailView 按鈕)
            await show_item_detail(interaction, gallery_id, show_cover=True)
            
        except Exception as e:
            logger.error(f"隨機一本失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
