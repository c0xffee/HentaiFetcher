"""
Read Detail View - 詳情頁互動視圖
==================================
功能：
- 開啟 PDF 按鈕
- nhentai 連結按鈕  
- 隨機一本按鈕
- 同作者/同原作搜尋按鈕
- Tag Select Menu 搜尋同標籤
- 重新下載按鈕
"""

import discord
from discord import ui
from typing import List, Optional
from urllib.parse import quote
import logging

from .base import BaseView, TIMEOUT_SECONDS

logger = logging.getLogger('HentaiFetcher.views')

PDF_WEB_BASE_URL = "http://192.168.0.32:8888"


class TagSelectMenu(ui.Select):
    """標籤選擇下拉選單"""
    
    def __init__(self, tags: List[str]):
        options = []
        
        # 最多顯示 25 個標籤
        for tag in tags[:25]:
            # 清理標籤顯示
            display_tag = tag[:50] if len(tag) > 50 else tag
            options.append(discord.SelectOption(
                label=display_tag,
                value=tag,
                emoji="🏷️"
            ))
        
        if not options:
            options.append(discord.SelectOption(
                label="無可用標籤",
                value="_none_"
            ))
        
        super().__init__(
            placeholder="🏷️ 選擇標籤搜尋同類作品...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="tag_select",
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
            # 執行搜尋
            from run import search_in_downloads, get_all_downloads_items, PDF_WEB_BASE_URL
            from eagle_library import EagleLibrary
            
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
                if selected_tag in item_tags:
                    if not any(r.get('nhentai_id') == item.get('nhentai_id') for r in results):
                        results.append(item)
            
            if not results:
                await interaction.followup.send(f"🔍 找不到包含標籤 `{selected_tag}` 的作品")
                return
            
            # 使用分頁 View 顯示所有結果
            from .search_view import SearchResultView
            
            view = SearchResultView(
                results, 
                selected_tag,
                search_type="tag"
            )
            
            await interaction.followup.send(embed=view.get_embed(), view=view)
            
        except Exception as e:
            logger.error(f"標籤搜尋失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 搜尋失敗: {e}", ephemeral=True)


class ReadDetailView(BaseView):
    """詳情頁互動視圖"""
    
    def __init__(
        self,
        gallery_id: str,
        title: str,
        item_source: str = "eagle",
        web_url: str = "",
        artists: List[str] = None,
        parodies: List[str] = None,
        characters: List[str] = None,
        other_tags: List[str] = None,
        *,
        timeout: float = TIMEOUT_SECONDS
    ):
        super().__init__(timeout=timeout)
        
        self.gallery_id = gallery_id
        self.title = title
        self.item_source = item_source
        self.web_url = web_url
        self.artists = artists or []
        self.parodies = parodies or []
        self.characters = characters or []
        self.other_tags = other_tags or []
        
        # Row 0: 主要按鈕
        # 開啟 PDF 按鈕 (Link Button) - 檢查 URL 長度
        from .helpers import build_safe_pdf_url
        
        pdf_url = build_safe_pdf_url(gallery_id, item_source, web_url)
        if pdf_url:
            pdf_button = ui.Button(
                label="📄 開啟 PDF",
                style=discord.ButtonStyle.link,
                url=pdf_url,
                row=0
            )
            self.add_item(pdf_button)
        
        # nhentai 連結 (永遠很短)
        nhentai_url = f"https://nhentai.net/g/{gallery_id}/"
        nhentai_button = ui.Button(
            label="🔗 nhentai",
            style=discord.ButtonStyle.link,
            url=nhentai_url,
            row=0
        )
        self.add_item(nhentai_button)
        
        # Row 1: 搜尋相關按鈕
        if self.artists:
            self.add_item(ArtistSearchButton(self.artists[0]))
        
        if self.parodies and self.parodies[0] != 'original':
            self.add_item(ParodySearchButton(self.parodies[0]))
        
        if self.characters:
            self.add_item(CharacterSearchButton(self.characters[0]))
        
        # Row 2: Tag Select Menu
        if self.other_tags:
            self.add_item(TagSelectMenu(self.other_tags))
        
        # Row 3: 其他操作 (移除重新下載按鈕)
        self.add_item(RandomButton())


class ArtistSearchButton(ui.Button):
    """搜尋同作者按鈕"""
    
    def __init__(self, artist: str):
        self.artist = artist
        super().__init__(
            label=f"🔍 同作者: {artist[:20]}",
            style=discord.ButtonStyle.secondary,
            custom_id=f"artist_search:{artist[:50]}",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            from run import search_in_downloads, get_all_downloads_items
            from eagle_library import EagleLibrary
            
            results = []
            search_tag = f"artist:{self.artist}"
            
            # 搜尋 Eagle
            try:
                eagle = EagleLibrary()
                eagle_results = eagle.find_by_tag(search_tag)
                for r in eagle_results:
                    r['source'] = 'eagle'
                    results.append(r)
            except Exception:
                pass
            
            # 搜尋 Downloads
            for item in get_all_downloads_items():
                item_tags = item.get('tags', [])
                if search_tag in item_tags:
                    if not any(r.get('nhentai_id') == item.get('nhentai_id') for r in results):
                        results.append(item)
            
            if not results:
                await interaction.followup.send(f"🔍 找不到作者 `{self.artist}` 的其他作品")
                return
            
            from .search_view import SearchResultView
            
            # 使用分頁 View 顯示所有結果
            view = SearchResultView(
                results, 
                f"artist:{self.artist}",
                search_type="artist"
            )
            
            await interaction.followup.send(embed=view.get_embed(), view=view)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 搜尋失敗: {e}", ephemeral=True)


class ParodySearchButton(ui.Button):
    """搜尋同原作按鈕"""
    
    def __init__(self, parody: str):
        self.parody = parody
        super().__init__(
            label=f"🔍 同原作: {parody[:20]}",
            style=discord.ButtonStyle.secondary,
            custom_id=f"parody_search:{parody[:50]}",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            from run import get_all_downloads_items
            from eagle_library import EagleLibrary
            
            results = []
            search_tag = f"parody:{self.parody}"
            
            # 搜尋 Eagle
            try:
                eagle = EagleLibrary()
                eagle_results = eagle.find_by_tag(search_tag)
                for r in eagle_results:
                    r['source'] = 'eagle'
                    results.append(r)
            except Exception:
                pass
            
            # 搜尋 Downloads
            for item in get_all_downloads_items():
                item_tags = item.get('tags', [])
                if search_tag in item_tags:
                    if not any(r.get('nhentai_id') == item.get('nhentai_id') for r in results):
                        results.append(item)
            
            if not results:
                await interaction.followup.send(f"🔍 找不到原作 `{self.parody}` 的其他作品")
                return
            
            from .search_view import SearchResultView
            
            # 使用分頁 View 顯示所有結果
            view = SearchResultView(
                results, 
                f"parody:{self.parody}",
                search_type="parody"
            )
            
            await interaction.followup.send(embed=view.get_embed(), view=view)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 搜尋失敗: {e}", ephemeral=True)


class CharacterSearchButton(ui.Button):
    """搜尋同角色按鈕"""
    
    def __init__(self, character: str):
        self.character = character
        super().__init__(
            label=f"🔍 同角色: {character[:20]}",
            style=discord.ButtonStyle.secondary,
            custom_id=f"character_search:{character[:50]}",
            row=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            from run import get_all_downloads_items
            from eagle_library import EagleLibrary
            
            results = []
            search_tag = f"character:{self.character}"
            
            # 搜尋 Eagle
            try:
                eagle = EagleLibrary()
                eagle_results = eagle.find_by_tag(search_tag)
                for r in eagle_results:
                    r['source'] = 'eagle'
                    results.append(r)
            except Exception:
                pass
            
            # 搜尋 Downloads
            for item in get_all_downloads_items():
                item_tags = item.get('tags', [])
                if search_tag in item_tags:
                    if not any(r.get('nhentai_id') == item.get('nhentai_id') for r in results):
                        results.append(item)
            
            if not results:
                await interaction.followup.send(f"🔍 找不到角色 `{self.character}` 的其他作品")
                return
            
            from .search_view import SearchResultView
            
            # 使用分頁 View 顯示所有結果
            view = SearchResultView(
                results, 
                f"character:{self.character}",
                search_type="character"
            )
            
            await interaction.followup.send(embed=view.get_embed(), view=view)
            
        except Exception as e:
            await interaction.followup.send(f"❌ 搜尋失敗: {e}", ephemeral=True)


class RandomButton(ui.Button):
    """隨機一本按鈕"""
    
    def __init__(self):
        super().__init__(
            label="🔀 隨機一本",
            style=discord.ButtonStyle.primary,
            custom_id="random_one",
            row=3
        )
    
    async def callback(self, interaction: discord.Interaction):
        """執行隨機抽選"""
        await interaction.response.defer()
        
        try:
            from run import get_all_downloads_items
            from eagle_library import EagleLibrary
            from .helpers import show_item_detail
            import secrets
            
            all_results = []
            
            # 從 Eagle 獲取
            try:
                eagle = EagleLibrary()
                eagle_results = eagle.get_all_items()
                for r in eagle_results:
                    r['source'] = 'eagle'
                all_results.extend(eagle_results)
            except Exception as e:
                logger.debug(f"Eagle 搜尋錯誤: {e}")
            
            # 從 Downloads 獲取
            download_results = get_all_downloads_items()
            all_results.extend(download_results)
            
            if not all_results:
                await interaction.followup.send("❌ 沒有可抽選的作品", ephemeral=True)
                return
            
            # 隨機選擇
            selected = secrets.choice(all_results)
            gallery_id = selected.get('nhentai_id', '')
            
            if not gallery_id:
                await interaction.followup.send("❌ 抽選結果無效", ephemeral=True)
                return
            
            # 使用統一模板顯示
            await show_item_detail(
                interaction, 
                gallery_id, 
                show_cover=True,
                title_prefix="🎲 **隨機抽選結果**"
            )
            
        except Exception as e:
            logger.error(f"隨機一本失敗: {e}", exc_info=True)
            await interaction.followup.send(f"❌ 操作失敗: {e}", ephemeral=True)
