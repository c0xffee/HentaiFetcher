"""
HentaiFetcher 斜線指令模組

此模組包含所有 Discord 斜線指令的實現。
指令按功能分類到不同的子模組中。

使用方式:
    from bot.commands import setup_commands
    await setup_commands(bot)
"""

from bot.commands.download import setup_download_commands
from bot.commands.info import setup_info_commands
from bot.commands.library import setup_library_commands
from bot.commands.admin import setup_admin_commands


def setup_commands(bot):
    """
    設定所有斜線指令到 Bot
    
    Args:
        bot: HentaiFetcherBot 實例
    """
    # 設定各類指令
    setup_download_commands(bot)
    setup_info_commands(bot)
    setup_library_commands(bot)
    setup_admin_commands(bot)


__all__ = ['setup_commands']
