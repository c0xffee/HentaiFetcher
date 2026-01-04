"""
Tag 管理相關斜線指令

精簡版指令:
- /tag list - 列出所有翻譯 (分頁、排序)
- /tag missing - 查看未翻譯標籤
- /tag update - 更新標籤翻譯 (只能修改已存在的)
- /tag reload - 重新載入字典
"""

import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Optional, List

from core.config import logger
from services.tag_translator import get_translator
from services.index_service import get_all_downloads_items
from eagle_library import EagleLibrary


class TagListView(ui.View):
    """Tag 列表分頁視圖"""
    
    def __init__(
        self,
        tags: List[tuple],  # [(tag, data), ...]
        sort_by: str = "local",
        page: int = 0,
        per_page: int = 15
    ):
        super().__init__(timeout=300)
        self.tags = tags
        self.sort_by = sort_by
        self.page = page
        self.per_page = per_page
        self.total_pages = max(1, (len(tags) + per_page - 1) // per_page)
        
        self._update_buttons()
    
    def _update_buttons(self):
        """更新按鈕狀態"""
        self.first_btn.disabled = self.page == 0
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1
        self.last_btn.disabled = self.page >= self.total_pages - 1
    
    def get_embed(self) -> discord.Embed:
        """生成 Embed"""
        translator = get_translator()
        stats = translator.get_stats()
        
        embed = discord.Embed(
            title="🏷️ 標籤翻譯字典",
            description=f"共 {stats['total_tags']} 個標籤 | 已翻譯 {stats['translated']} | 未翻譯 {stats['untranslated']}",
            color=discord.Color.blue()
        )
        
        # 排序說明
        sort_names = {
            "local": "📚 本地數量",
            "nhentai": "🌐 nhentai 數量",
            "alpha": "🔤 字母順序"
        }
        embed.add_field(
            name="排序方式",
            value=sort_names.get(self.sort_by, "📚 本地數量"),
            inline=True
        )
        embed.add_field(
            name="頁碼",
            value=f"{self.page + 1} / {self.total_pages}",
            inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # 空白欄
        
        # 取得當前頁的 tag
        start = self.page * self.per_page
        end = start + self.per_page
        page_tags = self.tags[start:end]
        
        # 建立列表
        lines = []
        for tag, data in page_tags:
            zh = data.get('zh', '')
            local = data.get('local_count', 0)
            nhentai = data.get('nhentai_count', 0)
            
            if zh:
                display = f"`{tag}` → **{zh}**"
            else:
                display = f"`{tag}` → ⚠️ _未翻譯_"
            
            # 數量顯示
            counts = []
            if local > 0:
                counts.append(f"📚{local}")
            if nhentai > 0:
                counts.append(f"🌐{nhentai:,}")
            
            if counts:
                display += f" ({', '.join(counts)})"
            
            lines.append(display)
        
        embed.add_field(
            name="標籤列表",
            value="\n".join(lines) if lines else "無資料",
            inline=False
        )
        
        embed.set_footer(text="使用 /tag update <英文> <中文> 更新翻譯")
        
        return embed
    
    @ui.button(label="⏮️", style=discord.ButtonStyle.secondary, custom_id="tag_first")
    async def first_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="◀️", style=discord.ButtonStyle.primary, custom_id="tag_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page = max(0, self.page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="▶️", style=discord.ButtonStyle.primary, custom_id="tag_next")
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="⏭️", style=discord.ButtonStyle.secondary, custom_id="tag_last")
    async def last_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page = self.total_pages - 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="📚 本地", style=discord.ButtonStyle.secondary, custom_id="sort_local", row=1)
    async def sort_local_btn(self, interaction: discord.Interaction, button: ui.Button):
        translator = get_translator()
        self.tags = translator.get_all_tags_sorted("local")
        self.sort_by = "local"
        self.page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🌐 nhentai", style=discord.ButtonStyle.secondary, custom_id="sort_nhentai", row=1)
    async def sort_nhentai_btn(self, interaction: discord.Interaction, button: ui.Button):
        translator = get_translator()
        self.tags = translator.get_all_tags_sorted("nhentai")
        self.sort_by = "nhentai"
        self.page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @ui.button(label="🔤 字母", style=discord.ButtonStyle.secondary, custom_id="sort_alpha", row=1)
    async def sort_alpha_btn(self, interaction: discord.Interaction, button: ui.Button):
        translator = get_translator()
        self.tags = translator.get_all_tags_sorted("alpha")
        self.sort_by = "alpha"
        self.page = 0
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class TagCommands(commands.Cog):
    """Tag 翻譯管理指令群組 (精簡版)"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    tag_group = app_commands.Group(name="tag", description="標籤翻譯管理")
    
    @tag_group.command(name="list", description="列出所有標籤翻譯")
    @app_commands.describe(
        sort="排序方式"
    )
    @app_commands.choices(sort=[
        app_commands.Choice(name="📚 本地數量", value="local"),
        app_commands.Choice(name="🌐 nhentai 數量", value="nhentai"),
        app_commands.Choice(name="🔤 字母順序", value="alpha"),
    ])
    async def tag_list(
        self,
        interaction: discord.Interaction,
        sort: str = "local"
    ):
        """列出所有翻譯"""
        await interaction.response.defer()
        
        translator = get_translator()
        tags = translator.get_all_tags_sorted(sort)
        
        if not tags:
            await interaction.followup.send("📭 字典是空的，尚無標籤")
            return
        
        view = TagListView(tags, sort_by=sort)
        await interaction.followup.send(embed=view.get_embed(), view=view)
    
    @tag_group.command(name="missing", description="查看未翻譯的標籤")
    async def tag_missing(
        self,
        interaction: discord.Interaction
    ):
        """查看未翻譯標籤"""
        await interaction.response.defer()
        
        translator = get_translator()
        missing = translator.get_untranslated()
        
        if not missing:
            await interaction.followup.send(
                "✅ 太棒了！目前沒有未翻譯的標籤"
            )
            return
        
        # 建立 Embed
        embed = discord.Embed(
            title="⚠️ 未翻譯標籤清單",
            description=f"共 {len(missing)} 個標籤尚未翻譯",
            color=discord.Color.orange()
        )
        
        # 顯示標籤
        tags_text = ", ".join([f"`{tag}`" for tag in missing[:50]])
        if len(missing) > 50:
            tags_text += f"\n... 還有 {len(missing) - 50} 個"
        
        embed.add_field(name="待翻譯", value=tags_text[:1024], inline=False)
        embed.set_footer(text="使用 /tag update <英文> <中文> 更新翻譯")
        
        await interaction.followup.send(embed=embed)
    
    @tag_group.command(name="update", description="更新標籤翻譯 (僅限已存在的標籤)")
    @app_commands.describe(
        english="英文標籤",
        chinese="繁體中文翻譯"
    )
    async def tag_update(
        self,
        interaction: discord.Interaction,
        english: str,
        chinese: str
    ):
        """更新標籤翻譯"""
        await interaction.response.defer()
        
        translator = get_translator()
        success, message = translator.update_translation(english, chinese)
        
        if success:
            await interaction.followup.send(f"✅ {message}")
            logger.info(f"Tag 翻譯更新: {english} → {chinese}")
        else:
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
    
    @tag_group.command(name="reload", description="重新載入標籤字典")
    async def tag_reload(
        self,
        interaction: discord.Interaction
    ):
        """重新載入字典"""
        await interaction.response.defer()
        
        translator = get_translator()
        count = translator.reload()
        stats = translator.get_stats()
        
        await interaction.followup.send(
            f"🔄 已重新載入標籤字典\n"
            f"📊 共 {stats['total_tags']} 個標籤 | 已翻譯 {stats['translated']} | 未翻譯 {stats['untranslated']}"
        )
        logger.info(f"Tag 字典重載: {count} 個標籤")


async def setup(bot: commands.Bot):
    """載入 Cog"""
    await bot.add_cog(TagCommands(bot))
