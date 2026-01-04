"""
Tag 管理相關斜線指令

包含:
- /tag add - 新增標籤翻譯
- /tag remove - 移除標籤翻譯
- /tag list - 列出所有翻譯
- /tag search - 搜尋翻譯
- /tag missing - 查看未翻譯標籤
- /tag reload - 重新載入字典
- /tag stats - 翻譯統計
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

from core.config import logger
from services.tag_translator import get_translator


class TagCommands(commands.Cog):
    """Tag 翻譯管理指令群組"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    tag_group = app_commands.Group(name="tag", description="標籤翻譯管理")
    
    @tag_group.command(name="add", description="新增或更新標籤翻譯")
    @app_commands.describe(
        english="英文標籤 (如: lolicon)",
        chinese="繁體中文翻譯 (如: 蘿莉控)"
    )
    async def tag_add(
        self,
        interaction: discord.Interaction,
        english: str,
        chinese: str
    ):
        """新增標籤翻譯"""
        await interaction.response.defer()
        
        translator = get_translator()
        
        # 檢查是否已存在
        existing = translator.translate(english, track_missing=False)
        is_update = existing != english
        
        # 新增翻譯
        success = translator.add_translation(english, chinese)
        
        if success:
            if is_update:
                await interaction.followup.send(
                    f"✅ 已更新標籤翻譯\n"
                    f"📝 `{english}` → `{chinese}`\n"
                    f"📊 原翻譯: `{existing}`"
                )
            else:
                await interaction.followup.send(
                    f"✅ 已新增標籤翻譯\n"
                    f"📝 `{english}` → `{chinese}`"
                )
            logger.info(f"Tag 翻譯{'更新' if is_update else '新增'}: {english} → {chinese}")
        else:
            await interaction.followup.send(
                f"❌ 新增翻譯失敗，請檢查輸入格式",
                ephemeral=True
            )
    
    @tag_group.command(name="remove", description="移除標籤翻譯")
    @app_commands.describe(english="要移除的英文標籤")
    async def tag_remove(
        self,
        interaction: discord.Interaction,
        english: str
    ):
        """移除標籤翻譯"""
        await interaction.response.defer()
        
        translator = get_translator()
        
        # 檢查是否存在
        existing = translator.translate(english, track_missing=False)
        if existing == english:
            await interaction.followup.send(
                f"⚠️ 找不到標籤 `{english}` 的翻譯",
                ephemeral=True
            )
            return
        
        # 移除翻譯
        success = translator.remove_translation(english)
        
        if success:
            await interaction.followup.send(
                f"🗑️ 已移除標籤翻譯\n"
                f"📝 `{english}` (原翻譯: `{existing}`)"
            )
            logger.info(f"Tag 翻譯移除: {english}")
        else:
            await interaction.followup.send(
                f"❌ 移除翻譯失敗",
                ephemeral=True
            )
    
    @tag_group.command(name="list", description="列出所有標籤翻譯")
    @app_commands.describe(page="頁碼 (每頁 30 筆)")
    async def tag_list(
        self,
        interaction: discord.Interaction,
        page: int = 1
    ):
        """列出所有翻譯"""
        await interaction.response.defer()
        
        translator = get_translator()
        all_tags = sorted(translator.dictionary.items())
        
        if not all_tags:
            await interaction.followup.send("📭 字典是空的，尚無翻譯")
            return
        
        # 分頁
        per_page = 30
        total_pages = (len(all_tags) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_tags = all_tags[start_idx:end_idx]
        
        # 建立 Embed
        embed = discord.Embed(
            title="🏷️ 標籤翻譯字典",
            description=f"共 {len(all_tags)} 個翻譯 | 第 {page}/{total_pages} 頁",
            color=discord.Color.blue()
        )
        
        # 分三欄顯示
        col_size = (len(page_tags) + 2) // 3
        for i in range(3):
            col_tags = page_tags[i * col_size:(i + 1) * col_size]
            if col_tags:
                field_value = "\n".join([f"`{en}` → {zh}" for en, zh in col_tags])
                embed.add_field(
                    name=f"📝 欄 {i + 1}",
                    value=field_value[:1024],  # Discord 欄位限制
                    inline=True
                )
        
        embed.set_footer(text=f"使用 /tag list {page + 1} 查看下一頁")
        
        await interaction.followup.send(embed=embed)
    
    @tag_group.command(name="search", description="搜尋標籤翻譯")
    @app_commands.describe(keyword="搜尋關鍵字 (英文或中文)")
    async def tag_search(
        self,
        interaction: discord.Interaction,
        keyword: str
    ):
        """搜尋翻譯"""
        await interaction.response.defer()
        
        translator = get_translator()
        results = translator.search(keyword)
        
        if not results:
            await interaction.followup.send(
                f"🔍 找不到包含 `{keyword}` 的翻譯",
                ephemeral=True
            )
            return
        
        # 建立 Embed
        embed = discord.Embed(
            title=f"🔍 搜尋結果: {keyword}",
            description=f"找到 {len(results)} 個相關翻譯",
            color=discord.Color.green()
        )
        
        # 顯示結果 (最多 25 筆)
        display_results = results[:25]
        result_text = "\n".join([f"`{en}` → **{zh}**" for en, zh in display_results])
        
        if len(results) > 25:
            result_text += f"\n... 還有 {len(results) - 25} 筆"
        
        embed.add_field(name="翻譯結果", value=result_text, inline=False)
        
        await interaction.followup.send(embed=embed)
    
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
                "✅ 太棒了！目前沒有未翻譯的標籤\n"
                "💡 使用本子後若遇到新標籤會自動追蹤"
            )
            return
        
        # 建立 Embed
        embed = discord.Embed(
            title="⚠️ 未翻譯標籤清單",
            description=f"共 {len(missing)} 個標籤尚未翻譯",
            color=discord.Color.orange()
        )
        
        # 顯示標籤 (最多 50 筆)
        display_tags = missing[:50]
        tags_text = ", ".join([f"`{tag}`" for tag in display_tags])
        
        if len(missing) > 50:
            tags_text += f"\n... 還有 {len(missing) - 50} 個"
        
        embed.add_field(name="待翻譯", value=tags_text[:1024], inline=False)
        embed.set_footer(text="使用 /tag add <英文> <中文> 新增翻譯")
        
        await interaction.followup.send(embed=embed)
    
    @tag_group.command(name="clear-missing", description="清空未翻譯追蹤清單")
    async def tag_clear_missing(
        self,
        interaction: discord.Interaction
    ):
        """清空未翻譯追蹤"""
        translator = get_translator()
        count = translator.get_untranslated_count()
        translator.clear_untranslated()
        
        await interaction.response.send_message(
            f"🗑️ 已清空未翻譯追蹤清單\n"
            f"📊 移除了 {count} 個追蹤項目"
        )
    
    @tag_group.command(name="reload", description="重新載入標籤字典")
    async def tag_reload(
        self,
        interaction: discord.Interaction
    ):
        """重新載入字典"""
        await interaction.response.defer()
        
        translator = get_translator()
        count = translator.reload()
        
        await interaction.followup.send(
            f"🔄 已重新載入標籤字典\n"
            f"📊 載入了 {count} 個翻譯"
        )
        logger.info(f"Tag 字典重載: {count} 個翻譯")
    
    @tag_group.command(name="stats", description="顯示翻譯統計")
    async def tag_stats(
        self,
        interaction: discord.Interaction
    ):
        """翻譯統計"""
        translator = get_translator()
        stats = translator.get_stats()
        
        embed = discord.Embed(
            title="📊 標籤翻譯統計",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📝 已翻譯",
            value=f"{stats['total_translations']} 個標籤",
            inline=True
        )
        embed.add_field(
            name="⚠️ 未翻譯",
            value=f"{stats['untranslated_count']} 個標籤",
            inline=True
        )
        embed.add_field(
            name="📁 字典位置",
            value=f"`{stats['dict_path']}`",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """載入 Cog"""
    await bot.add_cog(TagCommands(bot))
