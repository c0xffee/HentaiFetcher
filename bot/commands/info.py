"""
資訊類斜線指令

包含:
- /ping - 測試連線
- /version - 顯示版本
- /status - 顯示狀態
- /help - 顯示使用說明
"""

import re
import discord
from discord import app_commands

from core.config import (
    VERSION,
    logger,
    DEDICATED_CHANNEL_NAMES,
    DEDICATED_CHANNEL_IDS,
)
from core.batch_manager import download_queue


def setup_info_commands(bot):
    """設定資訊類指令到 Bot"""
    
    @bot.tree.command(name='ping', description='測試機器人連線')
    async def ping_command(interaction: discord.Interaction):
        """測試連線"""
        latency = round(bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! 延遲: {latency}ms")
    
    @bot.tree.command(name='version', description='顯示機器人版本')
    async def version_command(interaction: discord.Interaction):
        """顯示版本"""
        await interaction.response.send_message(f"📦 HentaiFetcher 版本: **{VERSION}**")
    
    @bot.tree.command(name='status', description='顯示機器人狀態')
    async def status_command(interaction: discord.Interaction):
        """顯示狀態"""
        embed = discord.Embed(
            title="📊 HentaiFetcher Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="佇列任務", value=str(download_queue.qsize()), inline=True)
        embed.add_field(name="延遲", value=f"{round(bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="伺服器數", value=str(len(bot.guilds)), inline=True)
        
        # 顯示目前下載狀態
        if bot.worker and bot.worker.current_task:
            match = re.search(r'/g/(\d+)', bot.worker.current_task)
            task_id = match.group(1) if match else "..."
            embed.add_field(name="目前下載", value=f"🔄 `{task_id}`", inline=True)
        else:
            embed.add_field(name="目前下載", value="⏳ 等待中", inline=True)
        
        embed.set_footer(text="使用 /dl <號碼> 開始下載")
        
        await interaction.response.send_message(embed=embed)
    
    @bot.tree.command(name='help', description='顯示使用說明')
    async def help_command(interaction: discord.Interaction):
        """顯示說明"""
        embed = discord.Embed(
            title="📖 HentaiFetcher 使用說明",
            description="自動下載漫畫並轉換為 PDF，生成 Eagle 相容 metadata",
            color=discord.Color.green()
        )
        
        # 檢查是否在專用頻道
        is_dedicated = (
            interaction.channel.name.lower() in [n.lower() for n in DEDICATED_CHANNEL_NAMES] or
            interaction.channel_id in DEDICATED_CHANNEL_IDS
        )
        
        if is_dedicated:
            embed.add_field(
                name="🎯 專用頻道模式（此頻道）",
                value="**所有指令都不需要前綴，直接輸入！**\n"
                      "━━━━━━━━━━━━━━━━━━\n"
                      "**📥 下載** - 直接貼網址或號碼：\n"
                      "```\n"
                      "421633\n"
                      "https://nhentai.net/g/607769/\n"
                      "```\n"
                      "**🧪 強制重新下載**：`test <號碼>`\n",
                inline=False
            )
        
        embed.add_field(
            name="📊 斜線指令",
            value="`/queue` - 查看佇列\n"
                  "`/status` - Bot 狀態\n"
                  "`/list` - 列出全部本子\n"
                  "`/random [數量] [來源]` - 隨機抽\n"
                  "`/fixcover` - 補充封面\n"
                  "`/cleanup` - 清除已導入項目",
            inline=True
        )
        
        embed.add_field(
            name="🦅 Eagle + 下載區",
            value="`/search <關鍵字> [來源]` - 搜尋\n"
                  "`/read <ID>` - 取得 PDF 連結\n"
                  "`/eagle` - Library 統計\n"
                  "`/reindex` - 重建索引\n"
                  "━━━━━━━━━━━━\n"
                  "🎮 **互動按鈕**: 搜尋/詳情頁支援點擊操作",
            inline=True
        )
        
        embed.add_field(
            name="🏷️ 標籤翻譯",
            value="`/tag list` - 列出字典\n"
                  "`/tag missing` - 未翻譯清單\n"
                  "`/tag update` - 更新翻譯\n"
                  "`/tag reload` - 重載字典",
            inline=True
        )
        
        embed.add_field(
            name="ℹ️ 系統",
            value="`/ping` - 測試連線\n"
                  "`/version` - 版本號\n"
                  "`/sync` - 同步指令 (管理員)\n"
                  "`/help` - 顯示此說明",
            inline=True
        )
        
        embed.add_field(
            name="📁 輸出結果",
            value="下載完成後會生成：\n"
                  "```\n"
                  "downloads/[Gallery_ID]/\n"
                  "├── [Gallery_ID].pdf\n"
                  "├── cover.jpg\n"
                  "└── metadata.json\n"
                  "```",
            inline=False
        )
        
        if is_dedicated:
            embed.set_footer(text="🎯 專用頻道：可直接貼號碼下載！")
        else:
            embed.set_footer(text="💡 使用斜線指令 / 開始")
        
        await interaction.response.send_message(embed=embed)
