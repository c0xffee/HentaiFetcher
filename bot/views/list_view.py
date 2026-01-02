"""
Paginated List View - 分頁列表互動視圖
======================================
功能：
- 上一頁/下一頁按鈕
- 頁碼顯示
- 快捷操作：搜尋、隨機
"""

import discord
from discord import ui
from typing import List, Tuple, Optional
import logging

from .base import BaseView, TIMEOUT_SECONDS

logger = logging.getLogger('HentaiFetcher.views')

# 每頁顯示數量
ITEMS_PER_PAGE = 15


class PaginatedListView(BaseView):
    """分頁列表互動視圖"""
    
    def __init__(
        self,
        items: List[Tuple[str, str, str]],  # (gallery_id, title, source)
        eagle_count: int = 0,
        downloads_count: int = 0,
        *,
        timeout: float = TIMEOUT_SECONDS
    ):
        super().__init__(timeout=timeout)
        
        self.items = items
        self.eagle_count = eagle_count
        self.downloads_count = downloads_count
        self.current_page = 0
        self.total_pages = max(1, (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        
        # 更新按鈕狀態
        self._update_buttons()
    
    def _update_buttons(self):
        """更新按鈕啟用狀態"""
        # 上一頁按鈕
        self.prev_button.disabled = (self.current_page <= 0)
        # 下一頁按鈕
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
        # 更新頁碼按鈕標籤
        self.page_button.label = f"{self.current_page + 1} / {self.total_pages}"
    
    def get_page_content(self) -> str:
        """取得當前頁面內容"""
        start_idx = self.current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.items))
        page_items = self.items[start_idx:end_idx]
        
        lines = []
        for i, (gallery_id, title, source) in enumerate(page_items, start=start_idx + 1):
            source_emoji = "🦅" if source == 'eagle' else "📁"
            # 截斷標題
            display_title = title[:45] + "..." if len(title) > 45 else title
            if gallery_id:
                lines.append(f"`{i}.` {source_emoji} **#{gallery_id}** {display_title}")
            else:
                lines.append(f"`{i}.` {source_emoji} {display_title}")
        
        return "\n".join(lines)
    
    def get_embed(self) -> discord.Embed:
        """建立 Embed"""
        embed = discord.Embed(
            title="📚 本子清單",
            description=self.get_page_content(),
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 統計",
            value=f"🦅 Eagle: **{self.eagle_count}** | 📁 下載: **{self.downloads_count}** | 📦 總計: **{len(self.items)}**",
            inline=False
        )
        
        embed.set_footer(text=f"頁 {self.current_page + 1}/{self.total_pages} | 使用 /read <ID> 查看詳情")
        
        return embed
    
    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary, custom_id="list_prev", row=0)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        """上一頁"""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="1 / 1", style=discord.ButtonStyle.primary, custom_id="list_page", disabled=True, row=0)
    async def page_button(self, interaction: discord.Interaction, button: ui.Button):
        """頁碼顯示 (不可點擊)"""
        await interaction.response.defer()
    
    @ui.button(label="➡️", style=discord.ButtonStyle.secondary, custom_id="list_next", row=0)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        """下一頁"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="⏮️ 首頁", style=discord.ButtonStyle.secondary, custom_id="list_first", row=1)
    async def first_button(self, interaction: discord.Interaction, button: ui.Button):
        """跳到首頁"""
        if self.current_page != 0:
            self.current_page = 0
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="⏭️ 末頁", style=discord.ButtonStyle.secondary, custom_id="list_last", row=1)
    async def last_button(self, interaction: discord.Interaction, button: ui.Button):
        """跳到末頁"""
        if self.current_page != self.total_pages - 1:
            self.current_page = self.total_pages - 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="🔀 隨機一本", style=discord.ButtonStyle.success, custom_id="list_random", row=1)
    async def random_button(self, interaction: discord.Interaction, button: ui.Button):
        """隨機抽選"""
        await interaction.response.send_message(
            "💡 請使用 `/random` 指令來隨機抽選",
            ephemeral=True
        )
    
    @ui.button(label="❌ 關閉", style=discord.ButtonStyle.danger, custom_id="list_close", row=1)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        """關閉列表"""
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
        except Exception:
            await interaction.response.send_message("❌ 無法刪除訊息", ephemeral=True)


class ListItemSelect(ui.Select):
    """列表項目選擇下拉選單"""
    
    def __init__(self, items: List[Tuple[str, str, str]], page: int = 0):
        self.items_map = {}
        
        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(items))
        page_items = items[start_idx:end_idx]
        
        options = []
        for gallery_id, title, source in page_items:
            if not gallery_id:
                continue  # 跳過沒有 ID 的項目
            
            source_emoji = "🦅" if source == 'eagle' else "📁"
            display_title = title[:50] if len(title) > 50 else title
            
            self.items_map[gallery_id] = (title, source)
            
            options.append(discord.SelectOption(
                label=display_title[:50],
                value=gallery_id,
                description=f"{source_emoji} ID: {gallery_id}",
                emoji=source_emoji
            ))
        
        if not options:
            options.append(discord.SelectOption(
                label="此頁無可選項目",
                value="_none_"
            ))
        
        super().__init__(
            placeholder="📖 選擇作品查看詳情...",
            min_values=1,
            max_values=1,
            options=options[:25],  # Discord 限制
            custom_id="list_select",
            row=2
        )
    
    async def callback(self, interaction: discord.Interaction):
        """選擇後執行"""
        selected_id = self.values[0]
        
        if selected_id == "_none_":
            await interaction.response.send_message("❌ 此頁無可選項目", ephemeral=True)
            return
        
        await interaction.response.send_message(
            f"💡 請使用 `/read {selected_id}` 查看完整詳情",
            ephemeral=True
        )
