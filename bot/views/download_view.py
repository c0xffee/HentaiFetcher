"""
Download Views - 下載相關互動視圖
=================================
功能：
- DownloadProgressView: 下載進行中視圖 (含取消按鈕)
- DownloadCompleteView: 下載完成互動視圖
"""

import discord
from discord import ui
from typing import Optional
from urllib.parse import quote
import logging

from .base import BaseView, TIMEOUT_SECONDS

logger = logging.getLogger('HentaiFetcher.views')

PDF_WEB_BASE_URL = "https://com1c.c0xffee.com"


class DownloadProgressView(BaseView):
    """下載進行中視圖 (含取消按鈕)"""
    
    def __init__(
        self,
        gallery_id: str,
        title: str,
        *,
        timeout: float = 600  # 10 分鐘超時 (下載可能需要較長時間)
    ):
        super().__init__(timeout=timeout)
        
        self.gallery_id = gallery_id
        self.title = title
        self.cancelled = False
        
        # nhentai 連結
        nhentai_url = f"https://nhentai.net/g/{gallery_id}/"
        nhentai_button = ui.Button(
            label="🔗 nhentai",
            style=discord.ButtonStyle.link,
            url=nhentai_url,
            row=0
        )
        self.add_item(nhentai_button)
    
    @ui.button(label="❌ 取消下載", style=discord.ButtonStyle.danger, custom_id="dl_cancel", row=0)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """取消下載"""
        from run import request_cancel, cancel_events
        
        if self.cancelled:
            await interaction.response.send_message("⚠️ 下載已經被取消", ephemeral=True)
            return
        
        # 請求取消
        cancelled = request_cancel(self.gallery_id)
        
        if cancelled:
            self.cancelled = True
            button.disabled = True
            button.label = "🚫 已取消"
            
            await interaction.response.edit_message(
                content=f"🚫 **下載已取消** - #{self.gallery_id}\n📖 {self.title}",
                view=self
            )
        else:
            # 顯示更詳細的錯誤資訊
            registered_ids = list(cancel_events.keys())
            debug_msg = f"⚠️ 無法取消 `#{self.gallery_id}`\n"
            debug_msg += f"📝 當前註冊的下載: {registered_ids if registered_ids else '無'}\n"
            debug_msg += "💡 可能原因: 下載已完成、尚未開始、或 Bot 已重啟"
            await interaction.response.send_message(debug_msg, ephemeral=True)
    
    def disable_cancel(self):
        """禁用取消按鈕（下載完成時調用）"""
        for item in self.children:
            if isinstance(item, ui.Button) and item.custom_id == "dl_cancel":
                self.remove_item(item)
                break


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
