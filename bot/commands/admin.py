"""
管理員相關斜線指令

包含:
- /sync - 強制同步斜線指令（管理員專用）
"""

import discord
from discord import app_commands

from core.config import logger


def setup_admin_commands(bot):
    """設定管理員相關指令到 Bot"""
    
    @bot.tree.command(name='sync', description='強制同步斜線指令（管理員專用）')
    async def sync_command(interaction: discord.Interaction):
        """強制同步斜線指令到 Discord"""
        # 檢查權限（只有管理員可以使用）
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 此指令僅限管理員使用", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 同步到當前伺服器
            bot.tree.copy_global_to(guild=interaction.guild)
            synced = await bot.tree.sync(guild=interaction.guild)
            await interaction.followup.send(f"✅ 已同步 **{len(synced)}** 個斜線指令到此伺服器\n💡 新參數應該立即生效", ephemeral=True)
            logger.info(f"手動同步指令到 {interaction.guild.name}: {len(synced)} 個")
        except Exception as e:
            await interaction.followup.send(f"❌ 同步失敗: {e}", ephemeral=True)
            logger.error(f"手動同步指令失敗: {e}")
