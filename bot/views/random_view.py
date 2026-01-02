"""
Random Result View - 隨機結果互動視圖
=====================================
功能：
- 查看詳情按鈕（直接執行）
- 開啟 PDF 按鈕
- 再抽一次按鈕（直接執行）
- 同作者搜尋按鈕
"""

import discord
from discord import ui
from typing import List, Optional, Dict, Any
from urllib.parse import quote
from pathlib import Path
import logging
import secrets

from .base import BaseView, TIMEOUT_SECONDS
from .helpers import build_safe_pdf_url, show_item_detail, DISCORD_URL_MAX_LENGTH

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
    
    @ui.button(label="📖 詳細資訊", style=discord.ButtonStyle.secondary, custom_id="random_detail", row=1)
    async def detail_button(self, interaction: discord.Interaction, button: ui.Button):
        """查看詳細資訊 - 使用統一模板"""
        await interaction.response.defer()
        
        try:
            await show_item_detail(interaction, self.gallery_id, show_cover=True)
        except Exception as e:
            logger.error(f"詳細資訊失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
    
    @ui.button(label="🔀 再抽一次", style=discord.ButtonStyle.primary, custom_id="random_again", row=1)
    async def random_again_button(self, interaction: discord.Interaction, button: ui.Button):
        """再抽一次 - 直接執行 random 邏輯"""
        await interaction.response.defer()
        
        try:
            from run import get_all_downloads_items
            from eagle_library import EagleLibrary
            from .helpers import send_cover_image, build_safe_pdf_url
            
            all_results = []
            
            if self.source_filter in ("all", "eagle"):
                try:
                    eagle = EagleLibrary()
                    eagle_results = eagle.get_all_items()
                    for r in eagle_results:
                        r['source'] = 'eagle'
                    all_results.extend(eagle_results)
                except Exception as e:
                    logger.debug(f"Eagle 搜尋錯誤: {e}")
            
            if self.source_filter in ("all", "downloads"):
                download_results = get_all_downloads_items()
                all_results.extend(download_results)
            
            if not all_results:
                await interaction.followup.send("❌ 沒有可抽選的作品", ephemeral=True)
                return
            
            # 隨機選擇
            selected = secrets.choice(all_results)
            
            gallery_id = selected.get('nhentai_id', '')
            title = selected.get('title', '未知')
            web_url = selected.get('web_url', '')
            folder_path = selected.get('folder_path', '')
            item_source = selected.get('source', 'eagle')
            tags = selected.get('tags', [])
            
            artists = [tag.replace('artist:', '') for tag in tags if isinstance(tag, str) and tag.startswith('artist:')]
            
            # 發送封面 (使用統一函數)
            await send_cover_image(interaction.channel, folder_path)
            
            # 建立訊息 - 使用安全的 URL
            msg_lines = []
            source_emoji = "🦅" if item_source == 'eagle' else "📁"
            msg_lines.append(f"🎲 **隨機抽選結果**")
            msg_lines.append(f"{source_emoji} **#{gallery_id}**")
            
            # 使用安全的 PDF URL
            safe_url = build_safe_pdf_url(gallery_id, item_source, web_url)
            if safe_url and len(safe_url) <= DISCORD_URL_MAX_LENGTH:
                msg_lines.append(f"📖 [{title}]({safe_url})")
            else:
                # fallback 到 nhentai
                nhentai_url = f"https://nhentai.net/g/{gallery_id}/"
                msg_lines.append(f"📖 [{title}]({nhentai_url})")
            
            if artists:
                msg_lines.append(f"✍️ 作者: {', '.join(artists)}")
            
            final_msg = "\n".join(msg_lines)
            
            # 建立新的 View - 傳入安全的 URL
            safe_web_url = web_url if len(web_url) <= DISCORD_URL_MAX_LENGTH else ""
            
            new_view = RandomResultView(
                gallery_id=gallery_id,
                title=title,
                item_source=item_source,
                web_url=safe_web_url,
                artists=artists,
                source_filter=self.source_filter
            )
            
            await interaction.channel.send(final_msg, view=new_view)
            
        except Exception as e:
            logger.error(f"再抽一次失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
    
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
