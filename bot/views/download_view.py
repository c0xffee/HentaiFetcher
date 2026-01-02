"""
Download Complete View - 下載完成互動視圖
=========================================
功能：
- 開啟 PDF 按鈕
- 查看詳情按鈕
- nhentai 連結按鈕
"""

import discord
from discord import ui
from typing import Optional
from urllib.parse import quote
import logging

from .base import BaseView, TIMEOUT_SECONDS

logger = logging.getLogger('HentaiFetcher.views')

PDF_WEB_BASE_URL = "http://192.168.0.32:8888"


class DownloadCompleteView(BaseView):
    """下載完成互動視圖"""
    
    def __init__(
        self,
        gallery_id: str,
        title: str,
        *,
        timeout: float = TIMEOUT_SECONDS
    ):
        super().__init__(timeout=timeout)
        
        self.gallery_id = gallery_id
        self.title = title
        
        # 開啟 PDF (Link Button)
        pdf_url = f"{PDF_WEB_BASE_URL}/{quote(gallery_id)}/{quote(gallery_id)}.pdf"
        pdf_button = ui.Button(
            label="📄 開啟 PDF",
            style=discord.ButtonStyle.link,
            url=pdf_url,
            row=0
        )
        self.add_item(pdf_button)
        
        # nhentai 連結
        nhentai_url = f"https://nhentai.net/g/{gallery_id}/"
        nhentai_button = ui.Button(
            label="🔗 nhentai",
            style=discord.ButtonStyle.link,
            url=nhentai_url,
            row=0
        )
        self.add_item(nhentai_button)
    
    @ui.button(label="📖 查看詳情", style=discord.ButtonStyle.secondary, custom_id="dl_detail", row=0)
    async def detail_button(self, interaction: discord.Interaction, button: ui.Button):
        """查看詳細資訊"""
        await interaction.response.send_message(
            f"💡 請使用 `/read {self.gallery_id}` 查看完整詳情",
            ephemeral=True
        )
    
    @ui.button(label="📥 繼續下載", style=discord.ButtonStyle.primary, custom_id="dl_continue", row=1)
    async def continue_button(self, interaction: discord.Interaction, button: ui.Button):
        """繼續下載提示"""
        await interaction.response.send_message(
            "💡 請直接貼上 nhentai 網址或 ID 來下載更多\n"
            "或使用 `/dl <ID>` 指令",
            ephemeral=True
        )
