"""
Search Result View - 搜尋結果互動視圖
=====================================
功能：
- Select Menu 選擇作品 → 執行 /read
- 按鈕：重新搜尋、隨機一本
"""

import discord
from discord import ui
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from urllib.parse import quote
import logging

from .base import BaseView, TIMEOUT_SECONDS

if TYPE_CHECKING:
    from discord import Interaction

logger = logging.getLogger('HentaiFetcher.views')

# PDF Web 基礎 URL
PDF_WEB_BASE_URL = "http://192.168.0.32:8888"


class SearchResultSelect(ui.Select):
    """搜尋結果下拉選單"""
    
    def __init__(self, results: List[Dict[str, Any]]):
        self.results_map: Dict[str, Dict[str, Any]] = {}
        
        options = []
        for i, item in enumerate(results[:25]):  # Discord 限制最多 25 個選項
            gallery_id = item.get('nhentai_id', 'N/A')
            title = item.get('title', '未知')
            source = item.get('source', 'eagle')
            source_emoji = "🦅" if source == 'eagle' else "📁"
            
            # 截斷標題 (Discord 限制 100 字元)
            if len(title) > 80:
                title = title[:77] + "..."
            
            # 儲存對應資料
            self.results_map[gallery_id] = item
            
            options.append(discord.SelectOption(
                label=f"{title[:50]}",
                value=gallery_id,
                description=f"{source_emoji} ID: {gallery_id}",
                emoji=source_emoji
            ))
        
        super().__init__(
            placeholder="📖 選擇作品查看詳情...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="search_select"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """選擇後執行 /read 邏輯"""
        selected_id = self.values[0]
        
        await interaction.response.defer()
        
        # 動態導入避免循環引用
        try:
            from run import find_item_by_id, parse_annotation_comments, PDF_WEB_BASE_URL
            from pathlib import Path
            
            result = find_item_by_id(selected_id)
            
            if not result:
                await interaction.followup.send(
                    f"🔍 找不到 ID `{selected_id}` 的本子",
                    ephemeral=True
                )
                return
            
            # 建立 ReadDetailView 並顯示
            from .read_view import ReadDetailView
            
            title = result.get('title', '未知')
            gallery_id = result.get('nhentai_id', selected_id)
            web_url = result.get('web_url', '')
            tags = result.get('tags', [])
            folder_path = result.get('folder_path', '')
            item_source = result.get('source', 'eagle')
            annotation = result.get('annotation', '')
            
            # 解析 tags
            artists = [tag.replace('artist:', '') for tag in tags if isinstance(tag, str) and tag.startswith('artist:')]
            parodies = [tag.replace('parody:', '') for tag in tags if isinstance(tag, str) and tag.startswith('parody:')]
            groups = [tag.replace('group:', '') for tag in tags if isinstance(tag, str) and tag.startswith('group:')]
            languages = [tag.replace('language:', '') for tag in tags if isinstance(tag, str) and tag.startswith('language:')]
            characters = [tag.replace('character:', '') for tag in tags if isinstance(tag, str) and tag.startswith('character:')]
            types = [tag.replace('type:', '') for tag in tags if isinstance(tag, str) and tag.startswith('type:')]
            other_tags = [tag for tag in tags if isinstance(tag, str) and not any(tag.startswith(prefix) for prefix in ['artist:', 'parody:', 'group:', 'language:', 'character:', 'type:'])]
            
            # 發送封面
            if folder_path:
                try:
                    folder = Path(folder_path)
                    for cover_name in ['cover.jpg', 'cover.png', 'cover.webp', 'thumbnail.png']:
                        cover_path = folder / cover_name
                        if cover_path.exists():
                            file = discord.File(str(cover_path), filename=cover_name)
                            await interaction.channel.send(file=file)
                            break
                    else:
                        # 找第一張圖
                        for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                            images = list(folder.glob(ext))
                            if images:
                                images.sort(key=lambda x: x.name)
                                file = discord.File(str(images[0]), filename=images[0].name)
                                await interaction.channel.send(file=file)
                                break
                except Exception as e:
                    logger.debug(f"封面發送失敗: {e}")
            
            # 建立資訊訊息
            msg_lines = []
            source_emoji = "🦅" if item_source == 'eagle' else "📁"
            
            msg_lines.append(f"{source_emoji} **#{gallery_id}**")
            
            # 標題連結
            if item_source == 'eagle' and web_url:
                msg_lines.append(f"📖 [{title}]({web_url})")
            elif item_source == 'downloads':
                pdf_url = f"{PDF_WEB_BASE_URL}/{quote(gallery_id)}/{quote(gallery_id)}.pdf"
                msg_lines.append(f"📖 [{title}]({pdf_url})")
            else:
                msg_lines.append(f"📖 **{title}**")
            
            msg_lines.append("")
            msg_lines.append(f"📦 來源: {'Eagle Library' if item_source == 'eagle' else '下載資料夾'}")
            
            if artists:
                msg_lines.append(f"✍️ 作者: {', '.join(artists)}")
            if groups:
                msg_lines.append(f"👥 社團: {', '.join(groups)}")
            if parodies:
                msg_lines.append(f"🎬 原作: {', '.join(parodies)}")
            if languages:
                msg_lines.append(f"🌐 語言: {', '.join(languages)}")
            if characters:
                msg_lines.append(f"👤 角色: {', '.join(characters)}")
            if types:
                msg_lines.append(f"📁 類型: {', '.join(types)}")
            
            # 評論
            if annotation:
                comments = parse_annotation_comments(annotation)
                if comments:
                    msg_lines.append("")
                    msg_lines.append("💬 評論:")
                    for c in comments[:3]:  # 只顯示前 3 則
                        msg_lines.append(f"  **{c['user']}**")
                        if c['content']:
                            msg_lines.append(f"  {c['content'][:100]}")
            
            # 標籤
            if other_tags:
                msg_lines.append("")
                tag_display = ', '.join([f'`{tag}`' for tag in other_tags[:15]])
                if len(other_tags) > 15:
                    tag_display += f" (+{len(other_tags) - 15})"
                msg_lines.append(f"🏷️ 標籤: {tag_display}")
            
            final_msg = "\n".join(msg_lines)
            if len(final_msg) > 1900:
                final_msg = final_msg[:1900] + "..."
            
            # 建立詳情頁 View
            view = ReadDetailView(
                gallery_id=gallery_id,
                title=title,
                item_source=item_source,
                web_url=web_url,
                artists=artists,
                parodies=parodies,
                other_tags=other_tags
            )
            
            await interaction.channel.send(final_msg, view=view)
            
        except Exception as e:
            logger.error(f"搜尋結果選擇失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)


class SearchResultView(BaseView):
    """搜尋結果互動視圖"""
    
    def __init__(
        self, 
        results: List[Dict[str, Any]], 
        query: str,
        source: str = "all",
        *,
        timeout: float = TIMEOUT_SECONDS
    ):
        super().__init__(timeout=timeout)
        
        self.query = query
        self.source = source
        self.results = results
        
        # 加入搜尋結果 Select Menu
        if results:
            self.add_item(SearchResultSelect(results))
    
    @ui.button(label="🔀 隨機一本", style=discord.ButtonStyle.primary, custom_id="search_random", row=1)
    async def random_button(self, interaction: discord.Interaction, button: ui.Button):
        """隨機抽選"""
        await interaction.response.defer()
        
        try:
            # 執行 /random 邏輯
            from run import bot
            
            # 找到 random 指令並執行
            random_cmd = bot.tree.get_command('random')
            if random_cmd:
                # 建立假的 Interaction 或直接呼叫函式
                from run import random_command
                # 這裡需要特殊處理，因為無法直接呼叫 slash command
                # 改為發送提示訊息
                await interaction.followup.send(
                    "💡 請使用 `/random` 指令來隨機抽選",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("❌ 找不到 random 指令", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
    
    @ui.button(label="❌ 關閉", style=discord.ButtonStyle.secondary, custom_id="search_close", row=1)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button):
        """關閉訊息"""
        try:
            await interaction.message.delete()
        except discord.NotFound:
            pass
        except Exception:
            await interaction.response.send_message("❌ 無法刪除訊息", ephemeral=True)
