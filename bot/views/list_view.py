"""
Paginated List View - 分頁列表互動視圖
======================================
功能：
- 上一頁/下一頁按鈕
- 頁碼顯示
- 作品選擇 Select Menu
- 排序功能：按收藏數、最新、隨機
- 快捷操作：隨機
"""

import discord
from discord import ui
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path
from urllib.parse import quote
import logging
import secrets

from .base import BaseView, TIMEOUT_SECONDS

logger = logging.getLogger('HentaiFetcher.views')

# 每頁顯示數量
ITEMS_PER_PAGE = 15
PDF_WEB_BASE_URL = "https://com1c.c0xffee.com"


class PaginatedListView(BaseView):
    """分頁列表互動視圖"""
    
    def __init__(
        self,
        items: List[Tuple[str, str, str]],  # (gallery_id, title, source)
        eagle_count: int = 0,
        downloads_count: int = 0,
        full_items: List[Dict[str, Any]] = None,  # 完整 item 資料 (用於排序)
        *,
        timeout: float = TIMEOUT_SECONDS
    ):
        super().__init__(timeout=timeout)
        
        self.items = items
        self.full_items = full_items or []
        self.eagle_count = eagle_count
        self.downloads_count = downloads_count
        self.current_page = 0
        self.total_pages = max(1, (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        self.sort_mode = "default"  # default, favorites, random
        
        # 加入 Select Menu
        self._update_select_menu()
        
        # 更新按鈕狀態
        self._update_buttons()
    
    def _update_select_menu(self):
        """更新 Select Menu"""
        # 移除舊的 Select
        for item in self.children[:]:
            if isinstance(item, ui.Select) and getattr(item, 'custom_id', '').startswith('list_select'):
                self.remove_item(item)
        
        select = ListItemSelect(self.items, self.current_page)
        self.add_item(select)
    
    def _update_buttons(self):
        """更新按鈕啟用狀態"""
        # 上一頁按鈕
        self.prev_button.disabled = (self.current_page <= 0)
        # 下一頁按鈕
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
        # 更新頁碼按鈕標籤
        self.page_button.label = f"{self.current_page + 1} / {self.total_pages}"
        # 更新排序按鈕標籤
        sort_labels = {
            "default": "📊 預設排序",
            "favorites": "⭐ 收藏數排序",
            "random": "🎲 隨機排序"
        }
        self.sort_button.label = sort_labels.get(self.sort_mode, "📊 排序")
    
    def _sort_items(self, mode: str):
        """排序項目"""
        if mode == "favorites" and self.full_items:
            # 按收藏數排序（需要完整資料）
            # 建立 id -> 收藏數 映射
            fav_map = {}
            for item in self.full_items:
                gid = item.get('nhentai_id', '')
                favs = item.get('favorites', 0)
                if gid:
                    fav_map[gid] = favs
            
            # 排序 items
            self.items.sort(key=lambda x: fav_map.get(x[0], 0), reverse=True)
        elif mode == "random":
            # 隨機排序
            import random
            random.shuffle(self.items)
        else:
            # 預設排序（按 ID）
            self.items.sort(key=lambda x: x[0] if x[0] and x[0].isdigit() else '0', reverse=True)
        
        self.sort_mode = mode
        self.current_page = 0
        self.total_pages = max(1, (len(self.items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    
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
        
        sort_labels = {"default": "預設", "favorites": "收藏數", "random": "隨機"}
        embed.set_footer(text=f"頁 {self.current_page + 1}/{self.total_pages} | 排序: {sort_labels.get(self.sort_mode, '預設')} | 使用下拉選單選擇作品")
        
        return embed
    
    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary, custom_id="list_prev", row=0)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        """上一頁"""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_select_menu()
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
            self._update_select_menu()
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="📊 預設排序", style=discord.ButtonStyle.secondary, custom_id="list_sort", row=2)
    async def sort_button(self, interaction: discord.Interaction, button: ui.Button):
        """切換排序模式"""
        # 循環排序模式
        modes = ["default", "favorites", "random"]
        current_idx = modes.index(self.sort_mode) if self.sort_mode in modes else 0
        next_mode = modes[(current_idx + 1) % len(modes)]
        
        self._sort_items(next_mode)
        self._update_select_menu()
        self._update_buttons()
        
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="⏮️ 首頁", style=discord.ButtonStyle.secondary, custom_id="list_first", row=2)
    async def first_button(self, interaction: discord.Interaction, button: ui.Button):
        """跳到首頁"""
        if self.current_page != 0:
            self.current_page = 0
            self._update_select_menu()
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="⏭️ 末頁", style=discord.ButtonStyle.secondary, custom_id="list_last", row=2)
    async def last_button(self, interaction: discord.Interaction, button: ui.Button):
        """跳到末頁"""
        if self.current_page != self.total_pages - 1:
            self.current_page = self.total_pages - 1
            self._update_select_menu()
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="🔀 隨機一本", style=discord.ButtonStyle.success, custom_id="list_random", row=3)
    async def random_button(self, interaction: discord.Interaction, button: ui.Button):
        """隨機抽選並直接顯示詳情"""
        await interaction.response.defer()
        
        try:
            if not self.items:
                await interaction.followup.send("❌ 沒有可選的項目", ephemeral=True)
                return
            
            # 隨機選一個
            selected = secrets.choice(self.items)
            gallery_id = selected[0]
            
            if not gallery_id:
                await interaction.followup.send("❌ 選中的項目沒有 ID", ephemeral=True)
                return
            
            # 執行 read 邏輯
            await self._show_detail(interaction, gallery_id)
            
        except Exception as e:
            logger.error(f"隨機選擇失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
    
    @ui.button(label="❌ 關閉", style=discord.ButtonStyle.danger, custom_id="list_close", row=3)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        """關閉列表"""
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
        except Exception:
            await interaction.response.send_message("❌ 無法刪除訊息", ephemeral=True)
    
    async def _show_detail(self, interaction: discord.Interaction, gallery_id: str):
        """顯示詳情 - 使用統一模板"""
        from .helpers import show_item_detail
        
        await show_item_detail(interaction, gallery_id, show_cover=True)


class ListItemSelect(ui.Select):
    """列表項目選擇下拉選單"""
    
    def __init__(self, items: List[Tuple[str, str, str]], page: int = 0):
        self.items_map = {}
        
        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(items))
        page_items = items[start_idx:end_idx]
        
        options = []
        seen_values = set()
        
        for i, (gallery_id, title, source) in enumerate(page_items):
            if not gallery_id:
                continue  # 跳過沒有 ID 的項目
            
            # 使用 index 確保唯一性
            unique_value = f"{start_idx + i}:{gallery_id}"
            if unique_value in seen_values:
                unique_value = f"{start_idx + i}:{gallery_id}:{i}"
            seen_values.add(unique_value)
            
            source_emoji = "🦅" if source == 'eagle' else "📁"
            display_title = title[:50] if len(title) > 50 else title
            
            self.items_map[unique_value] = gallery_id
            
            options.append(discord.SelectOption(
                label=display_title[:50],
                value=unique_value,
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
            custom_id=f"list_select_{page}",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """選擇後直接顯示詳情"""
        selected_value = self.values[0]
        
        if selected_value == "_none_":
            await interaction.response.send_message("❌ 此頁無可選項目", ephemeral=True)
            return
        
        # 解析 gallery_id
        gallery_id = self.items_map.get(selected_value)
        if not gallery_id:
            # 嘗試從 value 解析
            parts = selected_value.split(":")
            gallery_id = parts[1] if len(parts) >= 2 else selected_value
        
        await interaction.response.defer()
        
        try:
            # 使用父 View 的 _show_detail 方法
            parent_view = self.view
            if hasattr(parent_view, '_show_detail'):
                await parent_view._show_detail(interaction, gallery_id)
            else:
                await interaction.followup.send(f"💡 請使用 `/read {gallery_id}` 查看詳情", ephemeral=True)
        except Exception as e:
            logger.error(f"選擇結果失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
