"""
Random Result View - 隨機結果互動視圖
=====================================
功能：
- 查看詳情按鈕
- 開啟 PDF 按鈕
- 再抽一次按鈕
- 同作者搜尋按鈕
"""

import discord
from discord import ui
from typing import List, Optional
from urllib.parse import quote
import logging

from .base import BaseView, TIMEOUT_SECONDS

logger = logging.getLogger('HentaiFetcher.views')

PDF_WEB_BASE_URL = "http://192.168.0.32:8888"


class RandomResultView(BaseView):
    """隨機結果互動視圖"""
    
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
        
        # Row 0: 主要按鈕
        # 開啟 PDF (Link Button)
        if item_source == 'eagle' and web_url:
            pdf_button = ui.Button(
                label="📄 開啟 PDF",
                style=discord.ButtonStyle.link,
                url=web_url,
                row=0
            )
            self.add_item(pdf_button)
        elif item_source == 'downloads':
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
    
    @ui.button(label="📖 詳細資訊", style=discord.ButtonStyle.secondary, custom_id="random_detail", row=1)
    async def detail_button(self, interaction: discord.Interaction, button: ui.Button):
        """查看詳細資訊"""
        await interaction.response.send_message(
            f"💡 請使用 `/read {self.gallery_id}` 查看完整詳情",
            ephemeral=True
        )
    
    @ui.button(label="🔀 再抽一次", style=discord.ButtonStyle.primary, custom_id="random_again", row=1)
    async def random_again_button(self, interaction: discord.Interaction, button: ui.Button):
        """再抽一次"""
        await interaction.response.send_message(
            f"💡 請使用 `/random` 指令再抽一次\n"
            f"來源篩選: `{self.source_filter}`",
            ephemeral=True
        )
    
    @ui.button(label="📥 下載此本", style=discord.ButtonStyle.success, custom_id="random_download", row=1)
    async def download_button(self, interaction: discord.Interaction, button: ui.Button):
        """下載此本"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            from run import download_queue
            
            url = f"https://nhentai.net/g/{self.gallery_id}/"
            download_queue.put((url, interaction.channel_id, None, False, None))
            
            await interaction.followup.send(
                f"📥 已加入下載佇列: `{self.gallery_id}`",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
