"""
View Helpers - 共用工具函數
============================
提供各 View 共用的功能：
- 統一的詳情顯示模板
- URL 長度檢查與截斷
- 封面發送
"""

import discord
from typing import Dict, Any, List, Optional
from pathlib import Path
from urllib.parse import quote
import logging

logger = logging.getLogger('HentaiFetcher.views')

PDF_WEB_BASE_URL = "http://192.168.0.32:8888"
DISCORD_URL_MAX_LENGTH = 512


def truncate_url(url: str, max_length: int = DISCORD_URL_MAX_LENGTH) -> Optional[str]:
    """
    檢查並截斷 URL 以符合 Discord 限制
    
    Args:
        url: 原始 URL
        max_length: 最大長度 (Discord 限制 512)
    
    Returns:
        有效的 URL，或 None (如果無法使用)
    """
    if len(url) <= max_length:
        return url
    
    # 嘗試解析並截斷路徑部分
    # 如果 URL 太長，返回 None 讓調用者決定如何處理
    logger.warning(f"URL 超過 {max_length} 字符限制: {len(url)} 字符")
    return None


def build_safe_pdf_url(gallery_id: str, source: str = "downloads", web_url: str = "") -> Optional[str]:
    """
    建立安全的 PDF URL (確保不超過 512 字符)
    
    Args:
        gallery_id: nhentai Gallery ID
        source: 來源 (eagle/downloads)
        web_url: Eagle 的 web_url
    
    Returns:
        有效的 URL，或 None
    """
    if source == 'eagle' and web_url:
        # 檢查 Eagle URL 長度
        if len(web_url) <= DISCORD_URL_MAX_LENGTH:
            return web_url
        # 如果太長，返回 None (後面會 fallback 到 nhentai)
        return None
    elif source == 'downloads':
        # downloads 的 URL 通常很短
        pdf_url = f"{PDF_WEB_BASE_URL}/{quote(gallery_id)}/{quote(gallery_id)}.pdf"
        if len(pdf_url) <= DISCORD_URL_MAX_LENGTH:
            return pdf_url
        return None
    
    return None


async def send_cover_image(channel: discord.abc.Messageable, folder_path: str) -> bool:
    """
    發送封面圖片到頻道
    
    Args:
        channel: Discord 頻道
        folder_path: 資料夾路徑
    
    Returns:
        是否成功發送
    """
    if not folder_path:
        return False
    
    try:
        folder = Path(folder_path)
        
        # 優先使用 cover 檔案
        for cover_name in ['cover.jpg', 'cover.png', 'cover.webp', 'thumbnail.png']:
            cover_path = folder / cover_name
            if cover_path.exists():
                file = discord.File(str(cover_path), filename=cover_name)
                await channel.send(file=file)
                return True
        
        # 沒有 cover 就用第一張圖
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.webp']:
            images = list(folder.glob(ext))
            if images:
                images.sort(key=lambda x: x.name)
                file = discord.File(str(images[0]), filename=images[0].name)
                await channel.send(file=file)
                return True
                
    except Exception as e:
        logger.debug(f"封面發送失敗: {e}")
    
    return False


async def show_item_detail(
    interaction: discord.Interaction,
    gallery_id: str,
    *,
    show_cover: bool = True,
    title_prefix: str = ""
):
    """
    統一的詳情顯示模板
    
    所有地方顯示本子詳情都用這個函數，確保格式一致：
    - /read 指令
    - /random 詳細資訊按鈕
    - /list 選擇項目
    - /search 選擇結果
    
    Args:
        interaction: Discord Interaction (已 defer)
        gallery_id: nhentai Gallery ID
        show_cover: 是否顯示封面
        title_prefix: 標題前綴 (如 "🎲 隨機抽選結果")
    """
    from run import find_item_by_id, parse_annotation_comments
    from .read_view import ReadDetailView
    
    result = find_item_by_id(gallery_id)
    
    if not result:
        await interaction.followup.send(f"🔍 找不到 ID `{gallery_id}` 的本子", ephemeral=True)
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
    if show_cover and folder_path:
        await send_cover_image(interaction.channel, folder_path)
    
    # 建立資訊訊息
    msg_lines = []
    
    # 標題前綴
    if title_prefix:
        msg_lines.append(title_prefix)
    
    source_emoji = "🦅" if item_source == 'eagle' else "📁"
    msg_lines.append(f"{source_emoji} **#{gallery_id}**")
    
    # 標題連結 - 不檢查長度限制 (Discord 訊息內嵌連結無限制)
    if item_source == 'eagle' and web_url:
        msg_lines.append(f"📖 [{title}]({web_url})")
    elif item_source == 'downloads':
        pdf_url = f"{PDF_WEB_BASE_URL}/{quote(gallery_id)}/{quote(gallery_id)}.pdf"
        msg_lines.append(f"📖 [{title}]({pdf_url})")
    else:
        msg_lines.append(f"📖 **{title}**")
    
    msg_lines.append("")  # 空行
    
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
        char_display = ', '.join(characters[:5])
        if len(characters) > 5:
            char_display += f" (+{len(characters)-5})"
        msg_lines.append(f"👤 角色: {char_display}")
    
    # 檔案資訊
    info_parts = []
    if page_count > 0:
        info_parts.append(f"📄 {page_count} 頁")
    if file_size_str:
        info_parts.append(f"💾 {file_size_str}")
    if info_parts:
        msg_lines.append(" | ".join(info_parts))
    
    # 標籤顯示 (空格分隔，不用反引號)
    if other_tags:
        msg_lines.append("")
        tag_display = ' '.join(other_tags[:12])
        if len(other_tags) > 12:
            tag_display += f" (+{len(other_tags) - 12})"
        msg_lines.append(f"🏷️ {tag_display}")
    
    # 評論顯示
    if annotation:
        comments = parse_annotation_comments(annotation)
        if comments:
            msg_lines.append("")
            msg_lines.append("💬 **用戶評論**")
            for i, comment in enumerate(comments[:3]):
                user = comment.get('user', '匿名')
                content = comment.get('content', '')
                # 截斷過長評論
                if len(content) > 80:
                    content = content[:77] + "..."
                msg_lines.append(f"> **{user}**: {content}")
            if len(comments) > 3:
                msg_lines.append(f"> _... 還有 {len(comments) - 3} 則評論_")
    
    final_msg = "\n".join(msg_lines)
    
    # 截斷過長訊息
    if len(final_msg) > 1900:
        final_msg = final_msg[:1900] + "..."
    
    # 建立 View - PDF 按鈕會檢查 URL 長度，過長時不顯示按鈕
    view = ReadDetailView(
        gallery_id=gallery_id,
        title=title,
        item_source=item_source,
        web_url=web_url,  # 傳入原始 URL，ReadDetailView 會檢查長度
        artists=artists,
        parodies=parodies,
        characters=characters,
        other_tags=other_tags
    )
    
    await interaction.channel.send(final_msg, view=view)
