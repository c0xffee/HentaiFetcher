"""
庫管理相關斜線指令

包含:
- /list - 列出所有已下載的本子
- /random - 隨機顯示本子
- /search - 搜尋本子
- /read - 取得本子 PDF 連結
- /fixcover - 補充封面
- /cleanup - 清除已導入項目
- /eagle - Eagle Library 統計
- /reindex - 重建索引
"""

import re
import json
import asyncio
from pathlib import Path
from urllib.parse import quote

import discord
from discord import app_commands

from core.config import (
    logger,
    DOWNLOAD_DIR,
    PDF_WEB_BASE_URL,
)
from services.tag_translator import get_translator
from services.nhentai_api import (
    download_nhentai_cover,
    download_nhentai_first_page,
)
from services.index_service import (
    get_all_downloads_items,
    search_in_downloads,
    find_item_by_id,
    parse_annotation_comments,
)
from utils.helpers import get_first_image_as_cover


def setup_library_commands(bot):
    """設定庫管理相關指令到 Bot"""
    
    @bot.tree.command(name='list', description='列出所有已下載的本子（包含 Eagle Library）')
    async def list_command(interaction: discord.Interaction):
        """列出所有已下載的本子（分頁顯示）"""
        await interaction.response.defer()
        
        try:
            from eagle_library import EagleLibrary
            from bot.views import PaginatedListView
            
            # 收集所有項目
            items = []  # (gallery_id, title, source)
            seen_ids = set()
            
            # 1. 從 Eagle Library 獲取
            try:
                eagle = EagleLibrary()
                eagle_items = eagle.list_all()
                for item in eagle_items:
                    nid = item.get('nhentai_id', '')
                    title = item.get('title', item.get('folder_name', ''))
                    if nid:
                        seen_ids.add(nid)
                        items.append((nid, title, 'eagle'))
            except Exception as e:
                logger.debug(f"Eagle Library 載入失敗: {e}")
            
            # 2. 從 downloads 資料夾獲取（跳過已在 Eagle 中的）
            if DOWNLOAD_DIR.exists():
                folders = [f for f in DOWNLOAD_DIR.iterdir() if f.is_dir()]
                
                for folder in folders:
                    folder_name = folder.name
                    
                    # 嘗試從 metadata.json 獲取 gallery_id
                    metadata_path = folder / "metadata.json"
                    gallery_id = ""
                    title = folder_name
                    if metadata_path.exists():
                        try:
                            with open(metadata_path, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                                # 優先從 gallery_id 獲取
                                gallery_id = metadata.get('gallery_id', '')
                                # 如果沒有，從 URL 提取
                                if not gallery_id:
                                    url = metadata.get('url', '')
                                    match = re.search(r'/g/(\d+)', url)
                                    if match:
                                        gallery_id = match.group(1)
                                # 取得標題
                                title = metadata.get('name', folder_name)
                        except:
                            pass
                    
                    # 只加入不在 Eagle 中的
                    if gallery_id and gallery_id not in seen_ids:
                        items.append((gallery_id, title, 'downloads'))
                        seen_ids.add(gallery_id)
                    elif not gallery_id:
                        items.append(('', title, 'downloads'))
            
            if not items:
                await interaction.followup.send("📂 目前沒有任何本子")
                return
            
            # 按號碼排序（從小到大）
            items.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)
            
            # 統計來源數量
            eagle_count = sum(1 for _, _, src in items if src == 'eagle')
            downloads_count = sum(1 for _, _, src in items if src == 'downloads')
            
            # 建立分頁視圖
            view = PaginatedListView(
                items=items,
                eagle_count=eagle_count,
                downloads_count=downloads_count
            )
            
            # 發送帶有分頁的嵌入訊息
            await interaction.followup.send(embed=view.get_embed(), view=view)
            
        except Exception as e:
            logger.error(f"列出失敗: {e}")
            await interaction.followup.send(f"❌ 列出失敗: {e}")
    
    @bot.tree.command(name='random', description='隨機顯示本子（預設雙來源）')
    @app_commands.describe(
        count='顯示數量 (1-5)',
        source='來源：all=全部(預設), eagle=Eagle Library, downloads=下載資料夾'
    )
    @app_commands.choices(source=[
        app_commands.Choice(name='🔀 全部 (預設)', value='all'),
        app_commands.Choice(name='🦅 Eagle Library', value='eagle'),
        app_commands.Choice(name='📁 下載資料夾', value='downloads'),
    ])
    async def random_command(interaction: discord.Interaction, count: int = 1, source: str = 'all'):
        """隨機顯示本子 (優化版)"""
        await interaction.response.defer()
        
        try:
            import secrets
            
            # 限制數量
            count = max(1, min(count, 5))  # 1-5 本
            
            # 快速獲取 ID 列表 (不載入完整資訊)
            all_ids = []
            
            if source in ("all", "eagle"):
                try:
                    from eagle_library import EagleLibrary
                    eagle = EagleLibrary()
                    index = eagle._load_index()
                    for entry in index.get("imports", {}).values():
                        nid = entry.get("nhentaiId")
                        if nid and nid not in all_ids:
                            all_ids.append(nid)
                except Exception as e:
                    logger.debug(f"Eagle 索引讀取錯誤: {e}")
            
            if source in ("all", "downloads"):
                try:
                    if DOWNLOAD_DIR.exists():
                        for folder in DOWNLOAD_DIR.iterdir():
                            if folder.is_dir() and folder.name.isdigit():
                                if folder.name not in all_ids:
                                    all_ids.append(folder.name)
                except Exception as e:
                    logger.debug(f"Downloads 目錄讀取錯誤: {e}")
            
            if not all_ids:
                await interaction.followup.send("📂 沒有任何本子可供選擇")
                return
            
            # 隨機選擇 ID
            count = min(count, len(all_ids))
            selected_ids = set()
            while len(selected_ids) < count:
                idx = secrets.randbelow(len(all_ids))
                selected_ids.add(all_ids[idx])
            
            # 使用統一模板顯示
            from bot.views.helpers import show_item_detail
            
            for gallery_id in selected_ids:
                # show_item_detail 會處理封面、詳細資訊和 ReadDetailView 按鈕
                await show_item_detail(interaction, gallery_id, show_cover=True)
        
        except ImportError:
            await interaction.followup.send("❌ Eagle Library 模組未安裝")
        except Exception as e:
            logger.error(f"隨機顯示失敗: {e}")
            await interaction.followup.send(f"❌ 隨機顯示失敗: {e}")
    
    @bot.tree.command(name='search', description='搜尋本子 (Eagle Library + 下載資料夾)')
    @app_commands.describe(
        query='搜尋關鍵字或 nhentai ID',
        source='搜尋來源 (預設: all)'
    )
    @app_commands.choices(source=[
        app_commands.Choice(name="全部", value="all"),
        app_commands.Choice(name="Eagle Library", value="eagle"),
        app_commands.Choice(name="下載資料夾", value="downloads"),
    ])
    async def search_command(
        interaction: discord.Interaction, 
        query: str,
        source: str = "all"
    ):
        """搜尋本子 (支援雙來源)"""
        await interaction.response.defer()
        
        try:
            query = query.strip()
            results = []
            
            # 搜尋 Eagle Library
            if source in ['all', 'eagle']:
                try:
                    from eagle_library import EagleLibrary
                    eagle = EagleLibrary()
                    
                    if query.isdigit():
                        result = eagle.find_by_nhentai_id(query)
                        if result:
                            result['source'] = 'eagle'
                            results.append(result)
                    else:
                        eagle_results = eagle.find_by_title(query)
                        for r in eagle_results:
                            r['source'] = 'eagle'
                            results.append(r)
                except Exception as e:
                    logger.debug(f"Eagle 搜尋錯誤: {e}")
            
            # 搜尋 downloads 資料夾
            if source in ['all', 'downloads']:
                if query.isdigit():
                    # 用 ID 搜尋
                    for item in get_all_downloads_items():
                        if item.get('nhentai_id') == query:
                            # 避免重複（Eagle 已經有這個 ID）
                            if not any(r.get('nhentai_id') == query and r.get('source') == 'eagle' for r in results):
                                results.append(item)
                else:
                    # 用關鍵字搜尋
                    download_results = search_in_downloads(query)
                    for item in download_results:
                        # 避免 ID 重複
                        item_id = item.get('nhentai_id')
                        if not any(r.get('nhentai_id') == item_id for r in results):
                            results.append(item)
            
            # 顯示搜尋類型
            if query.isdigit():
                search_type = f"ID `{query}`"
            else:
                search_type = f"`{query}`"
            
            source_label = {"all": "全部", "eagle": "Eagle", "downloads": "下載區"}.get(source, source)
            
            if not results:
                await interaction.followup.send(f"🔍 在 **{source_label}** 中找不到符合 {search_type} 的結果")
                return
            
            total = len(results)
            display_results = results[:10]
            
            # 判斷是否使用精簡模式 (超過 5 個結果)
            compact_mode = total > 5
            
            if compact_mode:
                # 精簡模式：使用分頁 embed
                from bot.views import SearchResultView
                
                # 傳入全部結果，View 會處理分頁
                view = SearchResultView(results, query, source, search_type="keyword")
                await interaction.followup.send(embed=view.get_embed(), view=view)
            else:
                # 詳細模式：類似 random 的顯示方式
                await interaction.followup.send(f"🔍 **{source_label}** 中找到 {total} 個結果 - {search_type}")
                
                for item in display_results:
                    title = item.get('title', '未知')
                    gallery_id = item.get('nhentai_id', '未知')
                    web_url = item.get('web_url', '')
                    tags = item.get('tags', [])
                    folder_path = item.get('folder_path', '')
                    item_source = item.get('source', 'eagle')
                    
                    # 解析 tags
                    artists = [tag.replace('artist:', '') for tag in tags if isinstance(tag, str) and tag.startswith('artist:')]
                    parodies = [tag.replace('parody:', '') for tag in tags if isinstance(tag, str) and tag.startswith('parody:')]
                    
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
                    cover_sent = False
                    if folder_path:
                        try:
                            folder = Path(folder_path)
                            for cover_name in ['cover.jpg', 'cover.png', 'cover.webp', 'thumbnail.png']:
                                cover_path = folder / cover_name
                                if cover_path.exists():
                                    file = discord.File(str(cover_path), filename=cover_name)
                                    await interaction.channel.send(file=file)
                                    cover_sent = True
                                    break
                            
                            if not cover_sent:
                                for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                                    images = list(folder.glob(ext))
                                    if images:
                                        images.sort(key=lambda x: x.name)
                                        file = discord.File(str(images[0]), filename=images[0].name)
                                        await interaction.channel.send(file=file)
                                        cover_sent = True
                                        break
                        except Exception as e:
                            logger.debug(f"封面發送失敗: {e}")
                    
                    # 發送資訊
                    msg_lines = []
                    source_emoji = "🦅" if item_source == 'eagle' else "📁"
                    msg_lines.append(f"{source_emoji} **#{gallery_id}**")
                    
                    # 標題連結
                    if item_source == 'eagle' and web_url:
                        msg_lines.append(f"📖 [{title}]({web_url})")
                    elif item_source == 'downloads' and gallery_id:
                        pdf_url = f"{PDF_WEB_BASE_URL}/{quote(str(gallery_id))}/{quote(str(gallery_id))}.pdf"
                        msg_lines.append(f"📖 [{title}]({pdf_url})")
                    else:
                        msg_lines.append(f"📖 **{title}**")
                    
                    if artists:
                        msg_lines.append(f"✍️ {', '.join(artists)}")
                    if parodies:
                        msg_lines.append(f"🎬 {', '.join(parodies)}")
                    
                    # 加入檔案大小和頁數
                    info_parts = []
                    if page_count > 0:
                        info_parts.append(f"📄 {page_count} 頁")
                    if file_size_str:
                        info_parts.append(f"💾 {file_size_str}")
                    if info_parts:
                        msg_lines.append(" | ".join(info_parts))
                    
                    await interaction.channel.send("\n".join(msg_lines))
            
        except Exception as e:
            logger.error(f"搜尋失敗: {e}")
            await interaction.followup.send(f"❌ 搜尋失敗: {e}")
    
    @bot.tree.command(name='read', description='取得本子的 PDF 連結 (支援 Eagle + 下載區)')
    @app_commands.describe(nhentai_id='nhentai ID 或網址')
    async def read_command(interaction: discord.Interaction, nhentai_id: str):
        """取得本子的 PDF 連結 (支援雙來源)"""
        await interaction.response.defer()
        
        # 清理輸入
        nhentai_id = nhentai_id.strip()
        if not nhentai_id.isdigit():
            # 嘗試從網址提取
            match = re.search(r'/g/(\d+)', nhentai_id)
            if match:
                nhentai_id = match.group(1)
            else:
                await interaction.followup.send("❌ 請提供有效的 nhentai ID 或網址")
                return
        
        try:
            # 使用雙來源查詢
            result = find_item_by_id(nhentai_id)
            
            if not result:
                await interaction.followup.send(
                    f"🔍 找不到 ID `{nhentai_id}` 的本子\n"
                    f"💡 可能尚未下載，請使用 `/dl {nhentai_id}` 下載"
                )
                return
            
            title = result.get('title', '未知')
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
            cover_sent = False
            if folder_path:
                try:
                    folder = Path(folder_path)
                    for cover_name in ['cover.jpg', 'cover.png', 'cover.webp', 'thumbnail.png']:
                        cover_path = folder / cover_name
                        if cover_path.exists():
                            file = discord.File(str(cover_path), filename=cover_name)
                            await interaction.followup.send(file=file)
                            cover_sent = True
                            break
                    
                    if not cover_sent:
                        for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
                            images = list(folder.glob(ext))
                            if images:
                                images.sort(key=lambda x: x.name)
                                file = discord.File(str(images[0]), filename=images[0].name)
                                await interaction.followup.send(file=file)
                                cover_sent = True
                                break
                except Exception as e:
                    logger.debug(f"封面發送失敗: {e}")
            
            # 建立資訊訊息
            msg_lines = []
            source_emoji = "🦅" if item_source == 'eagle' else "📁"
            
            msg_lines.append(f"{source_emoji} **#{nhentai_id}**")
            
            # 標題連結
            if item_source == 'eagle' and web_url:
                msg_lines.append(f"📖 [{title}]({web_url})")
            elif item_source == 'downloads':
                pdf_url = f"{PDF_WEB_BASE_URL}/{quote(nhentai_id)}/{quote(nhentai_id)}.pdf"
                msg_lines.append(f"📖 [{title}]({pdf_url})")
            else:
                msg_lines.append(f"📖 **{title}**")
            
            msg_lines.append("")
            
            # 來源
            msg_lines.append(f"📦 來源: {'Eagle Library' if item_source == 'eagle' else '下載資料夾'}")
            
            # 基本資訊
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
            
            # 使用者評論 (顯示全部)
            if annotation:
                comments = parse_annotation_comments(annotation)
                if comments:
                    msg_lines.append("")
                    msg_lines.append("💬 評論:")
                    for c in comments:
                        msg_lines.append(f"  **{c['user']}**")
                        if c['content']:
                            msg_lines.append(f"  {c['content']}")
            
            # 標籤 (顯示全部，翻譯為繁中)
            if other_tags:
                msg_lines.append("")
                translator = get_translator()
                translated_tags = translator.translate_many(other_tags)
                msg_lines.append(f"🏷️ 標籤: {', '.join([f'`{tag}`' for tag in translated_tags])}")
            
            # 發送資訊
            final_msg = "\n".join(msg_lines)
            if len(final_msg) > 1900:
                final_msg = final_msg[:1900] + "..."
            
            # 建立詳情頁互動視圖
            from bot.views import ReadDetailView
            view = ReadDetailView(
                gallery_id=nhentai_id,
                title=title,
                item_source=item_source,
                web_url=web_url,
                artists=artists,
                parodies=parodies,
                other_tags=other_tags
            )
            
            if cover_sent:
                await interaction.channel.send(final_msg, view=view)
            else:
                await interaction.followup.send(final_msg, view=view)
            
        except Exception as e:
            logger.error(f"讀取失敗: {e}")
            await interaction.followup.send(f"❌ 讀取失敗: {e}")
    
    @bot.tree.command(name='fixcover', description='為已下載的本子補充封面')
    async def fixcover_command(interaction: discord.Interaction):
        """為已有的本子補充封面"""
        await interaction.response.defer()
        
        try:
            if not DOWNLOAD_DIR.exists():
                await interaction.followup.send("📂 下載資料夾不存在")
                return
            
            await interaction.followup.send("🔍 開始掃描並補充封面...")
            
            folders = [f for f in DOWNLOAD_DIR.iterdir() if f.is_dir()]
            fixed_count = 0
            skipped_count = 0
            fallback_count = 0  # 使用第一張圖片作為封面的數量
            failed_count = 0
            
            for folder in folders:
                # 檢查是否已有封面
                has_cover = any(list(folder.glob(f"cover.{ext}")) for ext in ['jpg', 'jpeg', 'png', 'gif', 'webp'])
                
                if has_cover:
                    skipped_count += 1
                    continue
                
                # 從 metadata.json 獲取 gallery_id
                metadata_path = folder / "metadata.json"
                gallery_id = ""
                
                if metadata_path.exists():
                    try:
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            # 從 url 提取 gallery_id
                            url = metadata.get('url', '')
                            match = re.search(r'/g/(\d+)', url)
                            if match:
                                gallery_id = match.group(1)
                    except Exception as e:
                        logger.error(f"讀取 metadata 失敗 ({folder.name}): {e}")
                
                cover_success = False
                
                if gallery_id:
                    # 嘗試從 nhentai 下載封面
                    if download_nhentai_cover(gallery_id, folder):
                        fixed_count += 1
                        cover_success = True
                        logger.info(f"補充封面成功 (nhentai 封面): {folder.name}")
                    else:
                        # 封面下載失敗，嘗試下載第一頁作為封面
                        await asyncio.sleep(0.3)  # 短暫延遲避免請求太快
                        if download_nhentai_first_page(gallery_id, folder):
                            fallback_count += 1
                            cover_success = True
                            logger.info(f"補充封面成功 (nhentai 第一頁): {folder.name}")
                    # 避免請求太頻繁
                    await asyncio.sleep(0.5)
                
                # 如果從 nhentai 都失敗，嘗試使用資料夾內的第一張圖片
                if not cover_success:
                    first_image = get_first_image_as_cover(folder)
                    if first_image:
                        fallback_count += 1
                        cover_success = True
                        logger.info(f"補充封面成功 (本地圖片): {folder.name}")
                    else:
                        failed_count += 1
                        logger.warning(f"補充封面失敗 (所有方法都失敗): {folder.name}")
            
            msg = f"✅ 完成！\n"
            msg += f"📥 從 nhentai 封面下載了 {fixed_count} 個\n"
            if fallback_count > 0:
                msg += f"🖼️ 使用備用方案 {fallback_count} 個\n"
            msg += f"⏭️ 跳過 {skipped_count} 個已有封面\n"
            if failed_count > 0:
                msg += f"❌ 失敗 {failed_count} 個"
            await interaction.channel.send(msg)
            
        except Exception as e:
            logger.error(f"補充封面失敗: {e}")
            await interaction.channel.send(f"❌ 補充封面失敗: {e}")
    
    @bot.tree.command(name='cleanup', description='清除 imported 資料夾中已導入 Eagle 的項目')
    async def cleanup_command(interaction: discord.Interaction):
        """清除 imported 資料夾中已導入到 Eagle 的項目"""
        await interaction.response.defer()
        
        try:
            # imported 資料夾路徑
            imported_dir = Path(DOWNLOAD_DIR).parent / 'imported'
            
            if not imported_dir.exists():
                await interaction.followup.send("📂 imported 資料夾不存在")
                return
            
            # 獲取 Eagle 索引
            from eagle_library import EagleLibrary
            eagle = EagleLibrary()
            
            # 先執行 reindex 確保索引最新
            await interaction.followup.send("🔄 正在掃描並比對 Eagle Library...")
            eagle.rebuild_index()
            
            folders = [f for f in imported_dir.iterdir() if f.is_dir()]
            can_delete = []  # 可以刪除的資料夾 (已在 Eagle 中)
            not_in_eagle = []  # 不在 Eagle 中的資料夾
            
            for folder in folders:
                folder_name = folder.name
                
                # 嘗試從資料夾名稱提取 gallery_id
                gallery_id = None
                
                # 方式 1: 純數字資料夾名
                if folder_name.isdigit():
                    gallery_id = folder_name
                else:
                    # 方式 2: 從 metadata.json 讀取
                    metadata_path = folder / 'metadata.json'
                    if metadata_path.exists():
                        try:
                            with open(metadata_path, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                                gallery_id = metadata.get('gallery_id') or metadata.get('nhentai_id')
                        except:
                            pass
                
                if gallery_id:
                    # 檢查是否在 Eagle 中
                    result = eagle.find_by_nhentai_id(str(gallery_id))
                    if result:
                        can_delete.append((folder, gallery_id, result.get('title', '')[:30]))
                    else:
                        not_in_eagle.append((folder, gallery_id))
                else:
                    # 沒有 ID 的資料夾，用標題搜尋
                    results = eagle.find_by_title(folder_name[:50])
                    if results:
                        can_delete.append((folder, None, folder_name[:30]))
                    else:
                        not_in_eagle.append((folder, None))
            
            if not can_delete:
                msg = f"✅ 沒有可清除的項目\n"
                msg += f"📁 imported 資料夾共 {len(folders)} 個項目\n"
                msg += f"⚠️ 其中 {len(not_in_eagle)} 個尚未導入 Eagle"
                await interaction.channel.send(msg)
                return
            
            # 顯示將要刪除的資料夾
            msg = f"🔍 發現 **{len(can_delete)}** 個已導入 Eagle 的項目可清除：\n\n"
            for folder, gid, title in can_delete[:10]:
                if gid:
                    msg += f"• `#{gid}` {title}\n"
                else:
                    msg += f"• {title}\n"
            if len(can_delete) > 10:
                msg += f"... 還有 {len(can_delete) - 10} 個\n"
            
            msg += f"\n📊 統計：已導入 {len(can_delete)} 個，未導入 {len(not_in_eagle)} 個"
            msg += "\n\n⚠️ **注意：只會刪除已確認導入 Eagle 的項目**"
            msg += "\n💡 未導入的項目會被保留"
            
            # 使用按鈕確認
            from bot.views import CleanupConfirmView
            view = CleanupConfirmView(
                can_delete=can_delete,
                not_in_eagle=not_in_eagle,
                user_id=interaction.user.id
            )
            
            await interaction.channel.send(msg, view=view)
            
        except Exception as e:
            logger.error(f"清除重複失敗: {e}")
            await interaction.followup.send(f"❌ 清除失敗: {e}")
    
    @bot.tree.command(name='eagle', description='顯示 Eagle Library 統計')
    async def eagle_stats_command(interaction: discord.Interaction):
        """顯示 Eagle Library 統計"""
        await interaction.response.defer()
        
        try:
            from eagle_library import EagleLibrary
            eagle = EagleLibrary()
            
            stats = eagle.get_stats()
            
            embed = discord.Embed(
                title="🦅 Eagle Library 統計",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="📚 已匯入", value=f"`{stats['total_count']}` 本", inline=True)
            embed.add_field(name="🔢 有 ID", value=f"`{stats['with_nhentai_id']}` 本", inline=True)
            
            if stats.get('last_updated'):
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(stats['last_updated'].replace('Z', '+00:00'))
                    embed.add_field(
                        name="🕐 最後更新",
                        value=dt.strftime("%Y-%m-%d %H:%M"),
                        inline=True
                    )
                except:
                    pass
            
            embed.set_footer(text="使用 /search <關鍵字> 搜尋 | /read <ID> 取得連結 | /reindex 重建索引")
            
            await interaction.followup.send(embed=embed)
            
        except ImportError:
            await interaction.followup.send("❌ Eagle Library 模組未安裝")
        except Exception as e:
            logger.error(f"統計失敗: {e}")
            await interaction.followup.send(f"❌ 統計失敗: {e}")
    
    @bot.tree.command(name='reindex', description='重建 Eagle Library 索引')
    async def reindex_command(interaction: discord.Interaction):
        """重建 Eagle Library 索引"""
        await interaction.response.defer()
        
        try:
            from eagle_library import EagleLibrary
            eagle = EagleLibrary()
            
            await interaction.followup.send("🔄 正在掃描 Eagle Library...")
            
            added = eagle.rebuild_index()
            stats = eagle.get_stats()
            
            if added > 0:
                await interaction.channel.send(f"✅ 索引重建完成！\n📥 新增 `{added}` 個項目\n📚 總計 `{stats['total_count']}` 本")
            else:
                await interaction.channel.send(f"✅ 索引已是最新！\n📚 總計 `{stats['total_count']}` 本")
            
        except ImportError:
            await interaction.followup.send("❌ Eagle Library 模組未安裝")
        except Exception as e:
            logger.error(f"重建索引失敗: {e}")
            await interaction.followup.send(f"❌ 重建索引失敗: {e}")
