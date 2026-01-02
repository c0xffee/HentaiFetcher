"""
Base View - 持久化視圖基礎類別
"""

import discord
from discord import ui
from typing import Optional
import logging

logger = logging.getLogger('HentaiFetcher.views')

# 超時時間：5 分鐘
TIMEOUT_SECONDS = 300


class BaseView(ui.View):
    """
    持久化視圖基礎類別
    
    特性：
    - 預設 5 分鐘超時
    - 支援持久化 (timeout=None 時)
    - 統一的錯誤處理
    """
    
    def __init__(self, *, timeout: Optional[float] = TIMEOUT_SECONDS, persistent: bool = False):
        """
        Args:
            timeout: 超時秒數，None 表示永不超時
            persistent: 是否為持久化 View (Bot 重啟後仍可運作)
        """
        if persistent:
            super().__init__(timeout=None)
        else:
            super().__init__(timeout=timeout)
        
        self.persistent = persistent
    
    async def on_timeout(self) -> None:
        """超時時禁用所有元件"""
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True
        
        # 嘗試更新訊息
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass  # 訊息已被刪除
            except Exception as e:
                logger.debug(f"更新超時訊息失敗: {e}")
    
    async def on_error(
        self, 
        interaction: discord.Interaction, 
        error: Exception, 
        item: ui.Item
    ) -> None:
        """統一錯誤處理"""
        logger.error(f"View 互動錯誤: {error}", exc_info=True)
        
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"❌ 操作失敗: {str(error)[:100]}", 
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ 操作失敗: {str(error)[:100]}", 
                    ephemeral=True
                )
        except Exception:
            pass  # 忽略回應失敗


class ConfirmView(BaseView):
    """確認對話框"""
    
    def __init__(self, *, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.value: Optional[bool] = None
    
    @ui.button(label='確認', style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()
    
    @ui.button(label='取消', style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()
