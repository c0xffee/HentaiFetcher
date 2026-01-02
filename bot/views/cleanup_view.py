"""
Cleanup Confirm View - 清理確認互動視圖
========================================
功能：
- 確認刪除按鈕
- 取消按鈕
- 只刪除已導入 Eagle 的項目
"""

import discord
from discord import ui
from typing import List, Tuple
from pathlib import Path
import shutil
import logging
import os
import stat
import time

from .base import BaseView, TIMEOUT_SECONDS

logger = logging.getLogger('HentaiFetcher.views')


def _remove_readonly(func, path, excinfo):
    """移除只讀屬性並重試刪除 (處理 Windows 檔案鎖定)"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception as e:
        # 如果還是失敗，嘗試等待一下再試
        time.sleep(0.1)
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except:
            logger.warning(f"無法刪除 {path}: {e}")


class CleanupConfirmView(BaseView):
    """清理確認互動視圖"""
    
    def __init__(
        self,
        can_delete: List[Tuple[Path, str, str]],  # (folder, gallery_id, title)
        not_in_eagle: List[Tuple[Path, str]],
        user_id: int,
        *,
        timeout: float = 60  # 1 分鐘超時
    ):
        super().__init__(timeout=timeout)
        
        self.can_delete = can_delete
        self.not_in_eagle = not_in_eagle
        self.user_id = user_id
        self.confirmed = False
    
    @ui.button(label="✅ 確認刪除 (只刪除已導入)", style=discord.ButtonStyle.danger, custom_id="cleanup_confirm", row=0)
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        """確認刪除"""
        # 檢查是否為原發起者
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ 只有指令發起者可以操作", ephemeral=True)
            return
        
        if self.confirmed:
            await interaction.response.send_message("⚠️ 已經執行過了", ephemeral=True)
            return
        
        self.confirmed = True
        
        # 禁用所有按鈕
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        
        await interaction.response.edit_message(
            content="🗑️ **正在刪除...**",
            view=self
        )
        
        # 執行刪除
        deleted = 0
        freed_size = 0
        
        failed_folders = []
        
        for folder, gid, title in self.can_delete:
            try:
                # 計算資料夾大小
                folder_size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
                freed_size += folder_size
                
                # 使用 onerror 處理 Windows 檔案鎖定
                shutil.rmtree(folder, onerror=_remove_readonly)
                
                # 確認是否真的刪除了
                if not folder.exists():
                    deleted += 1
                    logger.info(f"已刪除已導入項目: {folder.name}")
                else:
                    failed_folders.append((gid, "資料夾仍存在"))
            except Exception as e:
                failed_folders.append((gid, str(e)))
                logger.error(f"刪除失敗 {folder.name}: {e}")
        
        # 格式化釋放空間
        if freed_size > 1024 * 1024 * 1024:
            size_str = f"{freed_size / (1024*1024*1024):.2f} GB"
        elif freed_size > 1024 * 1024:
            size_str = f"{freed_size / (1024*1024):.1f} MB"
        else:
            size_str = f"{freed_size / 1024:.1f} KB"
        
        result_msg = f"✅ 已清除 **{deleted}/{len(self.can_delete)}** 個已導入項目\n"
        result_msg += f"💾 釋放空間: {size_str}\n"
        
        if failed_folders:
            result_msg += f"⚠️ 刪除失敗: {len(failed_folders)} 個 (檔案可能被佔用)\n"
        
        if self.not_in_eagle:
            result_msg += f"📁 保留未導入項目: {len(self.not_in_eagle)} 個"
        
        await interaction.channel.send(result_msg)
    
    @ui.button(label="❌ 取消", style=discord.ButtonStyle.secondary, custom_id="cleanup_cancel", row=0)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        """取消操作"""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⚠️ 只有指令發起者可以操作", ephemeral=True)
            return
        
        # 禁用所有按鈕
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True
        
        await interaction.response.edit_message(
            content="❌ **已取消操作**",
            view=self
        )
