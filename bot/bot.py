"""
HentaiFetcher Discord Bot 主類別

此模組包含 HentaiFetcherBot 類別，負責：
- Discord Bot 初始化與事件處理
- 專用頻道的直接下載模式
- 斜線指令同步
"""

import re
import discord
from discord.ext import commands
from typing import Optional

from core.config import (
    logger,
    DEDICATED_CHANNEL_NAMES,
    DEDICATED_CHANNEL_IDS,
)
from core.batch_manager import (
    download_queue,
    is_message_processed,
    generate_batch_id,
    init_batch,
)
from core.download_worker import DownloadWorker
from utils.url_parser import parse_input_to_urls
from services.index_service import check_already_downloaded
from services.nhentai_api import verify_nhentai_url


class HentaiFetcherBot(commands.Bot):
    """
    HentaiFetcher Discord Bot (使用 Slash Commands)
    """
    
    def __init__(self):
        # 設定 Intents
        intents = discord.Intents.default()
        intents.message_content = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None  # 使用自訂 help
        )
        
        self.worker: Optional[DownloadWorker] = None
    
    async def setup_hook(self):
        """Bot 啟動時的設定"""
        # 載入 Cog (包含 /tag 指令群組)
        from bot.commands import setup_cogs
        await setup_cogs(self)
        
        # 啟動工作執行緒
        self.worker = DownloadWorker(self)
        self.worker.start()
        logger.info("Bot setup 完成，下載執行緒已啟動")
    
    async def on_guild_join(self, guild):
        """加入新伺服器時同步指令"""
        try:
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info(f"已同步 {len(synced)} 個斜線指令到新伺服器: {guild.name}")
        except Exception as e:
            logger.error(f"同步斜線指令到 {guild.name} 失敗: {e}")
    
    async def on_ready(self):
        """Bot 連線成功時觸發"""
        logger.info(f'Bot 已登入: {self.user.name} (ID: {self.user.id})')
        logger.info(f'已連接到 {len(self.guilds)} 個伺服器')
        
        # 同步斜線指令到所有已加入的伺服器（即時生效）
        try:
            for guild in self.guilds:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f"✅ 已同步 {len(synced)} 個斜線指令到: {guild.name}")
        except Exception as e:
            logger.error(f"同步斜線指令失敗: {e}")
        
        # 設定狀態
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="#hentaifetcher"
            )
        )
        
        # 顯示專用頻道設定
        logger.info(f"專用頻道名稱: {DEDICATED_CHANNEL_NAMES}")
        logger.info("✅ Bot 已就緒！在專用頻道直接貼網址或數字即可下載")
    
    async def on_message(self, message):
        """處理訊息 - 支援專用頻道（不需 !dl）和傳統指令模式"""
        # 忽略 Bot 自己的訊息
        if message.author.bot:
            return
        
        # 訊息去重 - 避免重複處理
        if is_message_processed(message.id):
            print(f"[DEBUG] 跳過重複訊息: {message.id}", flush=True)
            return
        
        content = message.content.strip()
        
        # 忽略空訊息
        if not content:
            return
        
        # 檢查是否在專用頻道中
        is_dedicated_channel = (
            message.channel.name.lower() in [n.lower() for n in DEDICATED_CHANNEL_NAMES] or
            message.channel.id in DEDICATED_CHANNEL_IDS
        )
        
        # Debug: 記錄收到的訊息
        if is_dedicated_channel:
            print(f"[專用頻道] 收到訊息 (ID:{message.id}): {repr(content[:100])}", flush=True)
        else:
            print(f"[DEBUG] 收到訊息 (ID:{message.id}): {repr(content[:100])}", flush=True)
        
        # ===== 專用頻道模式：不需要 !dl 前綴 =====
        if is_dedicated_channel:
            # 忽略斜線指令（由 Discord 處理）
            if content.startswith('/'):
                return
            
            # 忽略 ! 前綴（舊指令格式，提示用戶使用斜線指令）
            if content.startswith('!'):
                await message.channel.send("💡 請使用斜線指令，例如：`/help`、`/search`")
                return
            
            # test 模式 - 強制重新下載
            content_lower = content.lower().strip()
            if content_lower.startswith('test ') or content_lower == 'test':
                await self._handle_test_mode(message, content)
                return
            
            # 處理下載請求（直接貼號碼或網址）
            await self.handle_direct_download(message, content)
            return
        
        # ===== 非專用頻道：提示使用斜線指令 =====
        if content.startswith('!'):
            await message.channel.send("💡 請使用斜線指令，例如：`/dl`、`/help`、`/search`")
            return
    
    async def _handle_test_mode(self, message, content: str):
        """處理 test 模式（強制重新下載）"""
        test_content = content[4:].strip() if len(content) > 4 else ''
        if not test_content:
            await message.channel.send(
                "🧪 **Test 模式使用方式（強制重新下載）**\n"
                "```\n"
                "test 421633\n"
                "```\n"
                "⚠️ 此模式會跳過重複檢查"
            )
            return
        
        # 解析 test 內容
        test_urls = parse_input_to_urls(test_content)
        if not test_urls:
            await message.channel.send(f"⚠️ 無法解析: `{test_content[:50]}`")
            return
        
        # 加入佇列（test 模式）
        queue_size = download_queue.qsize() + len(test_urls)
        gallery_ids = []
        for url in test_urls:
            match = re.search(r'/g/(\d+)', url)
            if match:
                gallery_ids.append(match.group(1))
        
        if len(test_urls) == 1 and gallery_ids:
            await message.channel.send(f"🧪 **#{gallery_ids[0]}** 已加入佇列（Test 模式）\n📊 佇列: {queue_size}")
            batch_id = None
        else:
            id_list = ", ".join([f"`{gid}`" for gid in gallery_ids[:10]])
            await message.channel.send(f"🧪 **{len(gallery_ids)}** 個已加入佇列（Test 模式）\n🔢 {id_list}\n📊 佇列: {queue_size}")
            # 多個下載啟用批次追蹤
            batch_id = generate_batch_id()
            init_batch(batch_id, len(test_urls), message.channel.id, gallery_ids)
        
        for url in test_urls:
            download_queue.put((url, message.channel.id, None, True, batch_id))
        
        logger.info(f"[專用頻道] 新增 {len(test_urls)} 個 TEST 下載任務 (來自: {message.author})" + (f" [批次: {batch_id}]" if batch_id else ""))
    
    async def handle_direct_download(self, message, content: str):
        """
        處理專用頻道中的直接下載請求
        不需要 ! 前綴，直接貼網址、數字或指令即可
        """
        content_lower = content.lower().strip()
        
        # ===== 處理指令（不需要 ! 前綴）=====
        command_handlers = {
            ('help', 'h'): 'help',
            ('queue', 'q'): 'queue',
            ('status',): 'status',
            ('ping',): 'ping',
            ('version', 'v'): 'version',
            ('list', 'ls', 'library'): 'list',
            ('cleanup', 'clean', 'dedup'): 'cleanup',
            ('fixcover', 'fc', 'addcover'): 'fixcover',
        }
        
        for aliases, cmd_name in command_handlers.items():
            if content_lower in aliases:
                ctx = await self.get_context(message)
                ctx.command = self.get_command(cmd_name)
                if ctx.command:
                    await self.invoke(ctx)
                return
        
        # random / rand / r [数量]
        if content_lower.startswith('random ') or content_lower.startswith('rand ') or content_lower.startswith('r ') or content_lower in ['random', 'rand', 'r']:
            # 提取数量参数
            parts = content.split()
            count = 1
            if len(parts) > 1:
                try:
                    count = int(parts[1])
                except:
                    count = 1
            
            # 直接调用函数（需要在 run.py 中定義 random_command）
            ctx = await self.get_context(message)
            # 這裡需要調用斜線指令的 random 功能
            # 暫時使用傳統指令
            ctx.command = self.get_command('random')
            if ctx.command:
                await self.invoke(ctx)
            return
        
        # dl <內容> - 也支援不帶 ! 的 dl
        if content_lower.startswith('dl ') or content_lower == 'dl':
            content = content[2:].strip() if len(content) > 2 else ''
            if not content:
                await message.channel.send(
                    "📖 **下載使用方式**\n"
                    "直接貼網址或號碼即可！\n"
                    "```\n"
                    "421633\n"
                    "421633 607769 613358\n"
                    "https://nhentai.net/g/421633/\n"
                    "```"
                )
                return
        
        # test <內容> - 強制重新下載（已在上層處理，這裡作為備用）
        if content_lower.startswith('test ') or content_lower == 'test':
            await self._handle_test_mode(message, content)
            return
        
        # 解析輸入
        parsed_urls = parse_input_to_urls(content)
        
        if not parsed_urls:
            # 如果無法解析，靜默忽略（不發送錯誤訊息，避免打擾）
            # 但如果內容看起來像是想要下載（純數字或包含 nhentai），給予提示
            if re.search(r'\d{4,7}', content) or 'nhentai' in content.lower():
                await message.channel.send(f"⚠️ 無法解析: `{content[:50]}`\n請確認格式正確（例如: `607769` 或 `https://nhentai.net/g/607769/`）")
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
                unique_urls.append(url)  # 無法解析的保留
        
        parsed_urls = unique_urls
        
        # 驗證並加入佇列
        valid_urls = []
        invalid_urls = []
        already_exists = []
        
        # 添加 reaction 表示處理中
        try:
            await message.add_reaction('⏳')
        except:
            pass
        
        # 下載前先執行快速 reindex (首個 URL)
        first_check = True
        
        for url in parsed_urls:
            # 提取 gallery ID
            match = re.search(r'/g/(\d+)', url)
            if match:
                gallery_id = match.group(1)
                
                # 先檢查是否已下載 (首個 URL 時觸發 reindex)
                exists, exist_info = check_already_downloaded(gallery_id, do_reindex=first_check)
                first_check = False  # 後續不再 reindex
                
                if exists:
                    already_exists.append((gallery_id, exist_info))
                    continue
                
                # 驗證是否可訪問
                is_valid, info = verify_nhentai_url(gallery_id)
                
                if is_valid:
                    valid_urls.append((url, gallery_id, info))
                else:
                    invalid_urls.append((gallery_id, info))
            else:
                invalid_urls.append((url, "無效格式"))
        
        # 移除處理中 reaction
        try:
            await message.remove_reaction('⏳', self.user)
        except:
            pass
        
        # 回報已存在的項目
        if already_exists:
            if len(already_exists) == 1:
                gid, info = already_exists[0]
                title = info.get('title', '')[:40]
                web_url = info.get('web_url', '')
                await message.channel.send(f"📚 **#{gid}** 已存在\n📖 {title}\n🔗 {web_url}")
            else:
                exist_list = "\n".join([f"• `{gid}`: {info.get('title', '')[:30]}" for gid, info in already_exists[:5]])
                await message.channel.send(f"📚 **{len(already_exists)}** 個已存在（跳過）:\n{exist_list}")
        
        # 處理無效的 URL
        if invalid_urls:
            error_list = "\n".join([f"• `{id}`: {reason}" for id, reason in invalid_urls[:5]])
            await message.channel.send(f"❌ 以下無法下載:\n{error_list}")
        
        # 加入有效的 URL
        if valid_urls:
            queue_size = download_queue.qsize() + len(valid_urls)
            gallery_id_list = [gid for _, gid, _ in valid_urls]
            
            # 發送簡化的狀態訊息（只顯示號碼）
            if len(valid_urls) == 1:
                _, gallery_id, _ = valid_urls[0]
                await message.channel.send(f"📥 **#{gallery_id}** 已加入佇列\n📊 佇列: {queue_size}")
                batch_id = None
            else:
                id_list = ", ".join([f"`{gid}`" for _, gid, _ in valid_urls[:10]])
                await message.channel.send(f"📥 **{len(valid_urls)}** 個已加入佇列\n🔢 {id_list}\n📊 佇列: {queue_size}")
                # 多個下載啟用批次追蹤
                batch_id = generate_batch_id()
                init_batch(batch_id, len(valid_urls), message.channel.id, gallery_id_list)
            
            # 添加成功 reaction 到原始訊息
            try:
                await message.add_reaction('✅')
            except:
                pass
            
            # 加入佇列（包含 batch_id）
            for url, gallery_id, title in valid_urls:
                download_queue.put((url, message.channel.id, None, False, batch_id))
            
            logger.info(f"[專用頻道] 新增 {len(valid_urls)} 個下載任務 (來自: {message.author})" + (f" [批次: {batch_id}]" if batch_id else ""))
    
    async def on_command_error(self, ctx, error):
        """全域錯誤處理"""
        if isinstance(error, commands.CommandNotFound):
            return  # 忽略未知指令
        
        logger.error(f"指令錯誤: {error}")
        await ctx.send(f"⚠️ 發生錯誤: {str(error)}")
