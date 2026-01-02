"""
Search Result View - 搜尋結果互動視圖 (支援分頁)
================================================
功能：
- Select Menu 選擇作品 → 執行 /read
- 分頁按鈕：上/下頁
- 隨機一本按鈕（直接執行）
- nhentai 連結按鈕
"""

import discord
from discord import ui
from typing import List, Dict, Any, Optional
from urllib.parse import quote
import logging
import secrets

from .base import BaseView, TIMEOUT_SECONDS

logger = logging.getLogger('HentaiFetcher.views')

PDF_WEB_BASE_URL = "https://com1c.c0xffee.com"
ITEMS_PER_PAGE = 10  # 每頁顯示數量


class SearchResultView(BaseView):
    """搜尋結果互動視圖 (支援分頁)"""
    
    def __init__(
        self, 
        results: List[Dict[str, Any]], 
        query: str,
        source: str = "all",
        search_type: str = "keyword",  # keyword, artist, tag, parody
        *,
        timeout: float = TIMEOUT_SECONDS
    ):
        super().__init__(timeout=timeout)
        
        self.query = query
        self.source = source
        self.results = results
        self.search_type = search_type
        self.current_page = 0
        self.total_pages = max(1, (len(results) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        self.sort_mode = "default"  # default, favorites, random
        self.original_results = results.copy()  # 保存原始順序
        
        # 建立 nhentai 連結 (Row 0)
        self._add_nhentai_link()
        
        # 加入搜尋結果 Select Menu (Row 1)
        self._update_select_menu()
        
        # 更新按鈕狀態
        self._update_buttons()
    
    def _add_nhentai_link(self):
        """加入 nhentai 連結按鈕"""
        nhentai_url = None
        
        if self.search_type == "artist":
            # artist:xxx -> xxx
            artist_name = self.query.replace("artist:", "").strip()
            nhentai_url = f"https://nhentai.net/artist/{quote(artist_name.replace(' ', '-').lower())}/"
        elif self.search_type == "tag":
            tag_name = self.query.strip()
            nhentai_url = f"https://nhentai.net/tag/{quote(tag_name.replace(' ', '-').lower())}/"
        elif self.search_type == "parody":
            parody_name = self.query.replace("parody:", "").strip()
            nhentai_url = f"https://nhentai.net/parody/{quote(parody_name.replace(' ', '-').lower())}/"
        elif self.search_type == "character":
            character_name = self.query.replace("character:", "").strip()
            nhentai_url = f"https://nhentai.net/character/{quote(character_name.replace(' ', '-').lower())}/"
        
        if nhentai_url:
            link_button = ui.Button(
                label="🔗 在 nhentai 查看",
                style=discord.ButtonStyle.link,
                url=nhentai_url,
                row=0
            )
            self.add_item(link_button)
    
    def _update_select_menu(self):
        """更新 Select Menu 選項"""
        # 移除舊的 Select Menu
        for item in self.children[:]:
            if isinstance(item, ui.Select) and getattr(item, 'custom_id', '').startswith('search_select'):
                self.remove_item(item)
        
        # 取得當前頁面的項目
        start_idx = self.current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.results))
        page_results = self.results[start_idx:end_idx]
        
        if page_results:
            select = SearchResultSelect(page_results, start_idx)
            self.add_item(select)
    
    def _update_buttons(self):
        """更新按鈕狀態"""
        self.prev_button.disabled = (self.current_page <= 0)
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
        self.page_button.label = f"{self.current_page + 1} / {self.total_pages}"
        # 更新排序按鈕標籤
        sort_labels = {
            "default": "📊 預設排序",
            "favorites": "⭐ 收藏數排序",
            "random": "🎲 隨機排序"
        }
        self.sort_button.label = sort_labels.get(self.sort_mode, "📊 排序")
    
    def _sort_results(self, mode: str):
        """排序結果"""
        import random as rand_module
        
        if mode == "favorites":
            # 按收藏數排序
            self.results.sort(key=lambda x: x.get('favorites', 0), reverse=True)
        elif mode == "random":
            # 隨機排序
            rand_module.shuffle(self.results)
        else:
            # 預設排序：恢復原始順序
            self.results = self.original_results.copy()
        
        self.sort_mode = mode
        self.current_page = 0
        self.total_pages = max(1, (len(self.results) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    
    def get_embed(self) -> discord.Embed:
        """取得當前頁面的 Embed"""
        start_idx = self.current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.results))
        page_results = self.results[start_idx:end_idx]
        
        # 標題
        if self.search_type == "artist":
            title = f"✍️ 同作者搜尋 - `{self.query.replace('artist:', '')}`"
            color = discord.Color.blue()
        elif self.search_type == "tag":
            title = f"🏷️ 標籤搜尋 - `{self.query}`"
            color = discord.Color.purple()
        elif self.search_type == "parody":
            title = f"🎬 同原作搜尋 - `{self.query.replace('parody:', '')}`"
            color = discord.Color.orange()
        elif self.search_type == "character":
            title = f"👤 同角色搜尋 - `{self.query.replace('character:', '')}`"
            color = discord.Color.green()
        else:
            title = f"🔍 搜尋結果 - `{self.query}`"
            color = discord.Color.blue()
        
        embed = discord.Embed(
            title=title,
            description=f"找到 {len(self.results)} 個結果",
            color=color
        )
        
        for i, r in enumerate(page_results, start=start_idx + 1):
            item_title = r.get('title', '未知')
            if len(item_title) > 45:
                item_title = item_title[:42] + "..."
            
            gallery_id = r.get('nhentai_id', 'N/A')
            item_source = r.get('source', 'eagle')
            source_emoji = "🦅" if item_source == 'eagle' else "📁"
            
            # 獲取收藏數
            favorites = r.get('favorites', 0)
            if not favorites:
                # 嘗試從 annotation 解析
                annotation = r.get('annotation', '')
                if annotation:
                    import re
                    match = re.search(r'❤️ 收藏數: (\d+)', annotation)
                    if match:
                        favorites = int(match.group(1))
            
            # ID 行顯示收藏數
            id_line = f"📖 ID: `{gallery_id}`"
            if favorites and favorites > 0:
                id_line += f" ❤️ {favorites}"
            
            embed.add_field(
                name=f"{source_emoji} {i}. {item_title}",
                value=id_line,
                inline=False
            )
        
        sort_labels = {"default": "預設", "favorites": "收藏數", "random": "隨機"}
        embed.set_footer(text=f"頁 {self.current_page + 1}/{self.total_pages} | 排序: {sort_labels.get(self.sort_mode, '預設')} | 使用下拉選單選擇作品")
        
        return embed
    
    @ui.button(label="⬅️", style=discord.ButtonStyle.secondary, custom_id="search_prev", row=2)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button):
        """上一頁"""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_select_menu()
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="1 / 1", style=discord.ButtonStyle.primary, custom_id="search_page", disabled=True, row=2)
    async def page_button(self, interaction: discord.Interaction, button: ui.Button):
        """頁碼顯示"""
        await interaction.response.defer()
    
    @ui.button(label="➡️", style=discord.ButtonStyle.secondary, custom_id="search_next", row=2)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button):
        """下一頁"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_select_menu()
            self._update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @ui.button(label="📊 預設排序", style=discord.ButtonStyle.secondary, custom_id="search_sort", row=2)
    async def sort_button(self, interaction: discord.Interaction, button: ui.Button):
        """切換排序模式"""
        # 循環排序模式
        modes = ["default", "favorites", "random"]
        current_idx = modes.index(self.sort_mode) if self.sort_mode in modes else 0
        next_mode = modes[(current_idx + 1) % len(modes)]
        
        self._sort_results(next_mode)
        self._update_select_menu()
        self._update_buttons()
        
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🔀 隨機一本", style=discord.ButtonStyle.success, custom_id="search_random", row=3)
    async def random_button(self, interaction: discord.Interaction, button: ui.Button):
        """從搜尋結果中隨機抽選一本並顯示詳情"""
        await interaction.response.defer()
        
        try:
            if not self.results:
                await interaction.followup.send("❌ 沒有可選的結果", ephemeral=True)
                return
            
            # 隨機選一個
            selected = secrets.choice(self.results)
            gallery_id = selected.get('nhentai_id')
            
            if not gallery_id:
                await interaction.followup.send("❌ 選中的項目沒有 ID", ephemeral=True)
                return
            
            # 執行 read 邏輯
            await self._show_detail(interaction, gallery_id)
            
        except Exception as e:
            logger.error(f"隨機選擇失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
    
    @ui.button(label="❌ 關閉", style=discord.ButtonStyle.danger, custom_id="search_close", row=3)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        """關閉訊息"""
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


class SearchResultSelect(ui.Select):
    """搜尋結果下拉選單"""
    
    def __init__(self, results: List[Dict[str, Any]], start_index: int = 0):
        self.results_list = results
        
        options = []
        seen_values = set()
        
        for i, item in enumerate(results[:25]):
            gallery_id = item.get('nhentai_id', '')
            title = item.get('title', '未知')
            source = item.get('source', 'eagle')
            source_emoji = "🦅" if source == 'eagle' else "📁"
            
            # 使用 index 確保 value 唯一
            unique_value = f"{start_index + i}:{gallery_id}"
            
            # 確保不重複
            if unique_value in seen_values:
                unique_value = f"{start_index + i}:{gallery_id}:{i}"
            seen_values.add(unique_value)
            
            # 截斷標題
            if len(title) > 50:
                title = title[:47] + "..."
            
            options.append(discord.SelectOption(
                label=title[:50],
                value=unique_value,
                description=f"{source_emoji} ID: {gallery_id}" if gallery_id else f"{source_emoji} 無 ID",
                emoji=source_emoji
            ))
        
        if not options:
            options.append(discord.SelectOption(label="無結果", value="_none_"))
        
        super().__init__(
            placeholder="📖 選擇作品查看詳情...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"search_select_{start_index}",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        """選擇後執行 /read 邏輯"""
        selected_value = self.values[0]
        
        if selected_value == "_none_":
            await interaction.response.send_message("❌ 無可選項目", ephemeral=True)
            return
        
        # 解析 value: "index:gallery_id" 或 "index:gallery_id:i"
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
