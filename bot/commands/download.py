"""
下載相關斜線指令

包含:
- /dl - 下載 nhentai 本子
- /queue - 查看下載佇列狀態
"""

import re
import discord
from discord import app_commands

from core.config import logger
from core.batch_manager import (
    download_queue,
    generate_batch_id,
    init_batch,
)
from utils.url_parser import parse_input_to_urls
from services.index_service import check_already_downloaded


def setup_download_commands(bot):
    """設定下載相關指令到 Bot"""
    
    @bot.tree.command(name='dl', description='下載 nhentai 本子')
    @app_commands.describe(
        gallery_ids='一個或多個 nhentai 號碼，用空格分隔',
        force='強制重新下載（跳過重複檢查）'
    )
    async def dl_command(interaction: discord.Interaction, gallery_ids: str, force: bool = False):
        """下載 nhentai 本子"""
        await interaction.response.defer()
        
        # 解析輸入
        parsed_urls = parse_input_to_urls(gallery_ids)
        
        if not parsed_urls:
            await interaction.followup.send("⚠️ 無法解析輸入。請提供有效的 nhentai 號碼。")
            return
        
        # 去除重複 URL (依據 gallery_id)
        seen_ids = set()
        unique_urls = []
        for url in parsed_urls:
            match = re.search(r'/g/(\d+)', url)
            if match:
                gid = match.group(1)
                if gid not in seen_ids:
                    seen_ids.add(gid)
                    unique_urls.append(url)
            else:
                unique_urls.append(url)
        parsed_urls = unique_urls
        
        # 如果不是強制模式，檢查重複
        new_urls = []
        already_exists = []
        
        if not force:
            # 下載前先執行快速 reindex (首個 URL)
            first_check = True
            
            for url in parsed_urls:
                match = re.search(r'/g/(\d+)', url)
                if match:
                    gallery_id = match.group(1)
                    # 首個 URL 時觸發 reindex
                    exists, info = check_already_downloaded(gallery_id, do_reindex=first_check)
                    first_check = False
                    
                    if exists:
                        already_exists.append((gallery_id, info))
                    else:
                        new_urls.append((url, gallery_id))
                else:
                    new_urls.append((url, None))
            
            # 回報已存在的項目
            if already_exists:
                if len(already_exists) == 1:
                    gid, info = already_exists[0]
                    title = info.get('title', '')[:40]
                    web_url = info.get('web_url', '')
                    await interaction.followup.send(f"📚 **#{gid}** 已存在\n📖 {title}\n🔗 {web_url}")
                else:
                    exist_list = "\n".join([f"• `{gid}`: {info.get('title', '')[:30]}" for gid, info in already_exists[:5]])
                    await interaction.followup.send(f"📚 **{len(already_exists)}** 個已存在（跳過）:\n{exist_list}")
            
            if not new_urls:
                return
        else:
            new_urls = [(url, re.search(r'/g/(\d+)', url).group(1) if re.search(r'/g/(\d+)', url) else None) for url in parsed_urls]
        
        # 加入佇列
        queue_size = download_queue.qsize() + len(new_urls)
        gallery_id_list = [gid for _, gid in new_urls if gid]
        
        mode_str = "（強制模式）" if force else ""
        if len(new_urls) == 1 and gallery_id_list:
            await interaction.followup.send(f"📥 **#{gallery_id_list[0]}** 已加入佇列{mode_str}\n📊 佇列: {queue_size}")
            # 單個下載不需要批次追蹤
            batch_id = None
        else:
            id_list = ", ".join([f"`{gid}`" for gid in gallery_id_list[:10]])
            await interaction.followup.send(f"📥 **{len(gallery_id_list)}** 個已加入佇列{mode_str}\n🔢 {id_list}\n📊 佇列: {queue_size}")
            # 多個下載啟用批次追蹤
            batch_id = generate_batch_id()
            init_batch(batch_id, len(new_urls), interaction.channel_id, gallery_id_list)
        
        # 加入佇列（包含 batch_id）
        for url, _ in new_urls:
            download_queue.put((url, interaction.channel_id, None, force, batch_id))
        
        logger.info(f"新增 {len(new_urls)} 個下載任務 (來自: {interaction.user})" + (f" [批次: {batch_id}]" if batch_id else ""))
    
    @bot.tree.command(name='queue', description='查看下載佇列狀態')
    async def queue_command(interaction: discord.Interaction):
        """查看下載佇列"""
        size = download_queue.qsize()
        await interaction.response.send_message(f"📊 佇列中等待任務: {size}")
