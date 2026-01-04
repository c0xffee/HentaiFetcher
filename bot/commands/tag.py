"""
Tag 管理相關斜線指令

精簡版指令:
- /tag - 列出所有翻譯 (分頁、排序、選擇搜尋)
- /tag missing - 查看未翻譯標籤
- /tag update - 更新標籤翻譯 (只能修改已存在的)
- /tag reload - 重新載入字典
- /tag sync - 同步 nhentai 計數
"""

import asyncio
import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Optional, List

from core.config import logger
from services.tag_translator import get_translator, fetch_nhentai_tag_count
from services.index_service import get_all_downloads_items
from eagle_library import EagleLibrary


class TagSelectMenu(ui.Select):
    """標籤選擇下拉選單 - 選擇後搜尋同標籤作品"""
    
    def __init__(self, tags: List[tuple], page: int = 0):
        """
        Args:
            tags: [(tag, data), ...] 當前頁的 tags
            page: 當前頁碼
        """
        options = []
        translator = get_translator()
        
        # 最多顯示 25 個標籤
        for tag, data in tags[:25]:
            zh = data.get('zh', '')
            local = data.get('local_count', 0)
            nhentai = data.get('nhentai_count', 0)
            
            # 顯示名稱: 中文 (英文) 或只有英文
            if zh:
                label = f"{zh}"[:50]
                description = f"{tag} | 📚{local} 🌐{nhentai:,}"[:100]
            else:
                label = f"{tag}"[:50]
                description = f"⚠️ 未翻譯 | 📚{local} 🌐{nhentai:,}"[:100]
            
            options.append(discord.SelectOption(
                label=label,
                value=tag,
                description=description,
                emoji="🏷️"
            ))
        
        if not options:
            options.append(discord.SelectOption(
                label="無可用標籤",
                value="_none_"
            ))
        
        super().__init__(
            placeholder="🔍 選擇標籤搜尋同類作品...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="tag_search_select",
            row=2
        )
    
    async def callback(self, interaction: discord.Interaction):
        """選擇標籤後搜尋"""
        selected_tag = self.values[0]
        
        if selected_tag == "_none_":
            await interaction.response.send_message("❌ 無可用標籤", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            translator = get_translator()
            translated = translator.translate(selected_tag, track_missing=False)
            
            results = []
            
            # 搜尋 Eagle
            try:
                eagle = EagleLibrary()
                eagle_results = eagle.find_by_tag(selected_tag)
                for r in eagle_results:
                    r['source'] = 'eagle'
                    results.append(r)
            except Exception as e:
                logger.debug(f"Eagle 搜尋錯誤: {e}")
            
            # 搜尋 Downloads
            for item in get_all_downloads_items():
                item_tags = item.get('tags', [])
                if selected_tag.lower() in [t.lower() for t in item_tags]:
                    if not any(r.get('nhentai_id') == item.get('nhentai_id') for r in results):
                        results.append(item)
            
            if not results:
                await interaction.followup.send(
                    f"🔍 找不到包含標籤 `{translated}` (`{selected_tag}`) 的作品"
                )
                return
            
            # 使用 SearchResultView 顯示
            from bot.views.search_view import SearchResultView
            
            view = SearchResultView(
                results, 
                translated,
                search_type="tag"
            )
            
            await interaction.followup.send(embed=view.get_embed(), view=view)
            
        except Exception as e:
            logger.error(f"標籤搜尋失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 搜尋失敗: {e}", ephemeral=True)


class TagListView(ui.View):
    """Tag 列表分頁視圖 (含選單搜尋)"""
    
    def __init__(
        self,
        tags: List[tuple],  # [(tag, data), ...]
        sort_by: str = "local",
        page: int = 0,
        per_page: int = 15
    ):
        super().__init__(timeout=300)
        self.all_tags = tags
        self.sort_by = sort_by
        self.page = page
        self.per_page = per_page
        self.total_pages = max(1, (len(tags) + per_page - 1) // per_page)
        
        self._update_view()
    
    def _get_page_tags(self) -> List[tuple]:
        """取得當前頁的 tags"""
        start = self.page * self.per_page
        end = start + self.per_page
        return self.all_tags[start:end]
    
    def _update_view(self):
        """更新按鈕狀態和選單"""
        # 更新分頁按鈕
        self.first_btn.disabled = self.page == 0
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1
        self.last_btn.disabled = self.page >= self.total_pages - 1
        
        # 移除舊的 Select Menu (row=2)
        to_remove = [item for item in self.children if isinstance(item, ui.Select)]
        for item in to_remove:
            self.remove_item(item)
        
        # 添加新的 Select Menu
        page_tags = self._get_page_tags()
        if page_tags:
            self.add_item(TagSelectMenu(page_tags, self.page))
    
    def get_message(self) -> str:
        """生成純文字訊息"""
        translator = get_translator()
        stats = translator.get_stats()
        
        # 排序說明
        sort_names = {
            "local": "📚 本地數量",
            "nhentai": "🌐 nhentai 數量",
            "alpha": "🔤 字母順序",
            "random": "🎲 隨機"
        }
        
        # 標題
        header = f"🏷️ **標籤翻譯字典** ({self.page + 1}/{self.total_pages})\n"
        header += f"共 **{stats['total_tags']}** 個 | ✅ {stats['translated']} 已翻譯 | 排序: {sort_names.get(self.sort_by, '📚 本地')}\n\n"
        
        # 取得當前頁的 tag
        page_tags = self._get_page_tags()
        
        # 建立列表 - 格式: 中文    📚 數量    🌐  數量    英文
        lines = []
        for tag, data in page_tags:
            zh = data.get('zh', '')
            local = data.get('local_count', 0)
            nhentai = data.get('nhentai_count', 0)
            
            zh_display = zh if zh else "⚠️未翻譯"
            
            # 格式: 中文    📚 22    🌐  23,750    english
            lines.append(f"{zh_display}    📚 {local}    🌐  {nhentai:,}    {tag}")
        
        content = header + "\n".join(lines)
        content += "\n\n*使用下拉選單搜尋同標籤作品*"
        
        return content
    
    @ui.button(label="⏮️", style=discord.ButtonStyle.secondary, custom_id="tag_first", row=0)
    async def first_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page = 0
        self._update_view()
        await interaction.response.edit_message(content=self.get_message(), embed=None, view=self)
    
    @ui.button(label="◀️", style=discord.ButtonStyle.primary, custom_id="tag_prev", row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page = max(0, self.page - 1)
        self._update_view()
        await interaction.response.edit_message(content=self.get_message(), embed=None, view=self)
    
    @ui.button(label="▶️", style=discord.ButtonStyle.primary, custom_id="tag_next", row=0)
    async def next_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_view()
        await interaction.response.edit_message(content=self.get_message(), embed=None, view=self)
    
    @ui.button(label="⏭️", style=discord.ButtonStyle.secondary, custom_id="tag_last", row=0)
    async def last_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.page = self.total_pages - 1
        self._update_view()
        await interaction.response.edit_message(content=self.get_message(), embed=None, view=self)
    
    @ui.button(label="📚 本地", style=discord.ButtonStyle.secondary, custom_id="sort_local", row=1)
    async def sort_local_btn(self, interaction: discord.Interaction, button: ui.Button):
        translator = get_translator()
        self.all_tags = translator.get_all_tags_sorted("local")
        self.sort_by = "local"
        self.page = 0
        self._update_view()
        await interaction.response.edit_message(content=self.get_message(), embed=None, view=self)
    
    @ui.button(label="🌐 nhentai", style=discord.ButtonStyle.secondary, custom_id="sort_nhentai", row=1)
    async def sort_nhentai_btn(self, interaction: discord.Interaction, button: ui.Button):
        translator = get_translator()
        self.all_tags = translator.get_all_tags_sorted("nhentai")
        self.sort_by = "nhentai"
        self.page = 0
        self._update_view()
        await interaction.response.edit_message(content=self.get_message(), embed=None, view=self)
    
    @ui.button(label="🔤 字母", style=discord.ButtonStyle.secondary, custom_id="sort_alpha", row=1)
    async def sort_alpha_btn(self, interaction: discord.Interaction, button: ui.Button):
        translator = get_translator()
        self.all_tags = translator.get_all_tags_sorted("alpha")
        self.sort_by = "alpha"
        self.page = 0
        self._update_view()
        await interaction.response.edit_message(content=self.get_message(), embed=None, view=self)
    
    @ui.button(label="🎲 隨機", style=discord.ButtonStyle.success, custom_id="sort_random", row=1)
    async def sort_random_btn(self, interaction: discord.Interaction, button: ui.Button):
        import random
        translator = get_translator()
        # 複製一份避免影響原始排序
        shuffled = list(translator.get_all_tags_sorted("local"))
        random.shuffle(shuffled)
        self.all_tags = shuffled
        self.sort_by = "random"
        self.page = 0
        self._update_view()
        await interaction.response.edit_message(content=self.get_message(), embed=None, view=self)


class TagCommands(commands.Cog):
    """Tag 翻譯管理指令群組"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    # 主指令: /tag - 直接顯示列表
    @app_commands.command(name="tag", description="顯示標籤翻譯字典 (分頁、排序、搜尋)")
    @app_commands.describe(sort="排序方式")
    @app_commands.choices(sort=[
        app_commands.Choice(name="📚 本地數量", value="local"),
        app_commands.Choice(name="🌐 nhentai 數量", value="nhentai"),
        app_commands.Choice(name="🔤 字母順序", value="alpha"),
    ])
    async def tag_main(
        self,
        interaction: discord.Interaction,
        sort: str = "local"
    ):
        """列出所有翻譯 (主指令)"""
        await interaction.response.defer()
        
        translator = get_translator()
        tags = translator.get_all_tags_sorted(sort)
        
        if not tags:
            await interaction.followup.send("📭 字典是空的，尚無標籤")
            return
        
        view = TagListView(tags, sort_by=sort)
        await interaction.followup.send(content=view.get_message(), view=view)
    
    # 子指令群組
    tagcmd = app_commands.Group(name="tagcmd", description="標籤管理指令")
    
    @tagcmd.command(name="missing", description="查看未翻譯的標籤")
    async def tag_missing(self, interaction: discord.Interaction):
        """查看未翻譯標籤"""
        await interaction.response.defer()
        
        translator = get_translator()
        missing = translator.get_untranslated()
        
        if not missing:
            await interaction.followup.send("✅ 太棒了！目前沒有未翻譯的標籤")
            return
        
        embed = discord.Embed(
            title="⚠️ 未翻譯標籤清單",
            description=f"共 {len(missing)} 個標籤尚未翻譯",
            color=discord.Color.orange()
        )
        
        tags_text = ", ".join([f"`{tag}`" for tag in missing[:50]])
        if len(missing) > 50:
            tags_text += f"\n... 還有 {len(missing) - 50} 個"
        
        embed.add_field(name="待翻譯", value=tags_text[:1024], inline=False)
        embed.set_footer(text="使用 /tag update <英文> <中文> 更新翻譯")
        
        await interaction.followup.send(embed=embed)
    
    @tagcmd.command(name="update", description="更新標籤翻譯 (僅限已存在的標籤)")
    @app_commands.describe(english="英文標籤", chinese="繁體中文翻譯")
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
    
    @tagcmd.command(name="reload", description="重新載入標籤字典")
    async def tag_reload(self, interaction: discord.Interaction):
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
    
    @tagcmd.command(name="sync", description="同步 nhentai 計數 (補齊缺失的數據)")
    async def tag_sync(self, interaction: discord.Interaction):
        """
        同步 nhentai 計數
        1. 補齊 nhentai_count = 0 的 tag
        2. 重新計算 local_count
        """
        await interaction.response.defer()
        
        translator = get_translator()
        
        # 找出需要更新 nhentai_count 的 tags
        tags_need_nhentai = []
        for tag, data in translator.dictionary.items():
            if data.get('nhentai_count', 0) == 0:
                tags_need_nhentai.append(tag)
        
        total = len(tags_need_nhentai)
        
        if total == 0:
            await interaction.followup.send("✅ 所有標籤都已有 nhentai 計數，無需同步")
            return
        
        # 發送初始訊息
        msg = await interaction.followup.send(
            f"🔄 開始同步 nhentai 計數...\n"
            f"📊 共 {total} 個標籤需要更新",
            wait=True
        )
        
        success_count = 0
        fail_count = 0
        failed_tags = []  # 記錄失敗的 tag
        
        # 批量抓取 (每 5 個更新一次進度)
        for i, tag in enumerate(tags_need_nhentai):
            try:
                count = await fetch_nhentai_tag_count(tag)
                if count > 0:
                    translator.dictionary[tag]['nhentai_count'] = count
                    success_count += 1
                else:
                    fail_count += 1
                    failed_tags.append(tag)
                
                # 避免請求過快
                await asyncio.sleep(0.5)
                
                # 每 10 個更新進度
                if (i + 1) % 10 == 0 or (i + 1) == total:
                    progress = (i + 1) / total * 100
                    await msg.edit(content=(
                        f"🔄 同步中... {progress:.0f}%\n"
                        f"✅ 成功: {success_count} | ❌ 失敗: {fail_count} | 📊 進度: {i + 1}/{total}"
                    ))
                    
            except Exception as e:
                logger.error(f"同步 tag '{tag}' 失敗: {e}")
                fail_count += 1
                failed_tags.append(f"{tag} (錯誤)")
        
        # 重新計算 local_count
        await msg.edit(content=f"🔄 重新計算本地數量...")
        
        # 重置所有 local_count
        for tag in translator.dictionary:
            translator.dictionary[tag]['local_count'] = 0
        
        # 計算 Eagle
        try:
            eagle = EagleLibrary()
            for item in eagle.get_all_items():
                tags = item.get('tags', [])
                for tag in tags:
                    tag_lower = tag.lower()
                    if tag_lower in translator.dictionary:
                        translator.dictionary[tag_lower]['local_count'] += 1
        except Exception as e:
            logger.debug(f"Eagle 計算失敗: {e}")
        
        # 計算 Downloads
        for item in get_all_downloads_items():
            tags = item.get('tags', [])
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in translator.dictionary:
                    translator.dictionary[tag_lower]['local_count'] += 1
        
        # 儲存
        translator.save()
        
        # 構建結果訊息
        result_msg = (
            f"✅ 同步完成!\n"
            f"📊 nhentai 計數: 成功 {success_count} / 失敗 {fail_count}\n"
            f"📚 本地計數: 已重新計算"
        )
        
        # 如果有失敗的 tag，顯示清單
        if failed_tags:
            failed_list = ", ".join([f"`{t}`" for t in failed_tags[:30]])
            if len(failed_tags) > 30:
                failed_list += f" ... 還有 {len(failed_tags) - 30} 個"
            result_msg += f"\n\n⚠️ **以下 tag 在 nhentai 上找不到:**\n{failed_list}"
        
        await msg.edit(content=result_msg)
        
        logger.info(f"Tag sync 完成: nhentai={success_count}/{total}, failed={failed_tags[:10]}")


async def setup(bot: commands.Bot):
    """載入 Cog"""
    await bot.add_cog(TagCommands(bot))
