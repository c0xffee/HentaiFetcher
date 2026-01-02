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
        """查看詳細資訊 - 直接執行 read 邏輯"""
        await interaction.response.defer()
        
        try:
            from run import find_item_by_id, parse_annotation_comments
            from .read_view import ReadDetailView
            
            result = find_item_by_id(self.gallery_id)
            
            if not result:
                await interaction.followup.send(f"🔍 找不到 ID `{self.gallery_id}` 的本子", ephemeral=True)
                return
            
            title = result.get('title', '未知')
            web_url = result.get('web_url', '')
            tags = result.get('tags', [])
            folder_path = result.get('folder_path', '')
            item_source = result.get('source', 'eagle')
            
            # 解析 tags
            artists = [tag.replace('artist:', '') for tag in tags if isinstance(tag, str) and tag.startswith('artist:')]
            parodies = [tag.replace('parody:', '') for tag in tags if isinstance(tag, str) and tag.startswith('parody:')]
            groups = [tag.replace('group:', '') for tag in tags if isinstance(tag, str) and tag.startswith('group:')]
            languages = [tag.replace('language:', '') for tag in tags if isinstance(tag, str) and tag.startswith('language:')]
            characters = [tag.replace('character:', '') for tag in tags if isinstance(tag, str) and tag.startswith('character:')]
            other_tags = [tag for tag in tags if isinstance(tag, str) and not any(tag.startswith(prefix) for prefix in ['artist:', 'parody:', 'group:', 'language:', 'character:', 'type:'])]
            
            # 計算檔案大小和頁數
            file_size_str = ""
            page_count = 0
            if folder_path:
                try:
                    folder = Path(folder_path)
                    # 計算 PDF 檔案大小
                    pdf_files = list(folder.glob('*.pdf'))
                    if pdf_files:
                        pdf_size = pdf_files[0].stat().st_size
                        if pdf_size > 1024 * 1024:
                            file_size_str = f"{pdf_size / (1024*1024):.1f} MB"
                        else:
                            file_size_str = f"{pdf_size / 1024:.0f} KB"
                    
                    # 計算頁數 (圖片數量)
                    image_exts = ['*.jpg', '*.jpeg', '*.png', '*.webp', '*.gif']
                    for ext in image_exts:
                        page_count += len(list(folder.glob(ext)))
                except Exception as e:
                    logger.debug(f"計算檔案資訊失敗: {e}")
            
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
            msg_lines.append(f"{source_emoji} **#{self.gallery_id}**")
            
            if item_source == 'eagle' and web_url:
                msg_lines.append(f"📖 [{title}]({web_url})")
            elif item_source == 'downloads':
                pdf_url = f"{PDF_WEB_BASE_URL}/{quote(self.gallery_id)}/{quote(self.gallery_id)}.pdf"
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
                msg_lines.append(f"👤 角色: {', '.join(characters[:3])}" + (f" (+{len(characters)-3})" if len(characters) > 3 else ""))
            
            # 加入檔案大小和頁數
            info_parts = []
            if page_count > 0:
                info_parts.append(f"📄 {page_count} 頁")
            if file_size_str:
                info_parts.append(f"💾 {file_size_str}")
            if info_parts:
                msg_lines.append(" | ".join(info_parts))
            
            if other_tags:
                msg_lines.append("")
                tag_display = ', '.join([f'`{tag}`' for tag in other_tags[:15]])
                if len(other_tags) > 15:
                    tag_display += f" (+{len(other_tags) - 15})"
                msg_lines.append(f"🏷️ 標籤: {tag_display}")
            
            final_msg = "\n".join(msg_lines)
            if len(final_msg) > 1900:
                final_msg = final_msg[:1900] + "..."
            
            view = ReadDetailView(
                gallery_id=self.gallery_id,
                title=title,
                item_source=item_source,
                web_url=web_url,
                artists=artists,
                parodies=parodies,
                characters=characters,
                other_tags=other_tags
            )
            
            await interaction.channel.send(final_msg, view=view)
            
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
                        for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                            images = list(folder.glob(ext))
                            if images:
                                images.sort(key=lambda x: x.name)
                                file = discord.File(str(images[0]), filename=images[0].name)
                                await interaction.channel.send(file=file)
                                break
                except Exception as e:
                    logger.debug(f"封面發送失敗: {e}")
            
            # 建立訊息
            msg_lines = []
            source_emoji = "🦅" if item_source == 'eagle' else "📁"
            msg_lines.append(f"🎲 **隨機抽選結果**")
            msg_lines.append(f"{source_emoji} **#{gallery_id}**")
            
            if item_source == 'eagle' and web_url:
                msg_lines.append(f"📖 [{title}]({web_url})")
            elif item_source == 'downloads':
                pdf_url = f"{PDF_WEB_BASE_URL}/{quote(gallery_id)}/{quote(gallery_id)}.pdf"
                msg_lines.append(f"📖 [{title}]({pdf_url})")
            else:
                msg_lines.append(f"📖 **{title}**")
            
            if artists:
                msg_lines.append(f"✍️ 作者: {', '.join(artists)}")
            
            final_msg = "\n".join(msg_lines)
            
            # 建立新的 View
            new_view = RandomResultView(
                gallery_id=gallery_id,
                title=title,
                item_source=item_source,
                web_url=web_url,
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
