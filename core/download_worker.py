#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher Download Worker
=============================
下載工作執行緒：從佇列中取出任務並執行
"""

import re
import time
import asyncio
import threading
from queue import Empty
from pathlib import Path
from typing import Optional, Dict, Any

import discord

from core.config import logger, PROGRESS_UPDATE_INTERVAL, SECONDS_PER_PAGE
from core.batch_manager import (
    download_queue, 
    register_cancel_event, 
    unregister_cancel_event, 
    is_cancelled,
    update_batch
)
from core.download_processor import DownloadProcessor
from utils.helpers import create_progress_bar
from services.nhentai_api import get_nhentai_page_count


class DownloadWorker(threading.Thread):
    """
    下載工作執行緒：從佇列中取出任務並執行
    """
    
    def __init__(self, bot):
        super().__init__(daemon=True)
        self.bot = bot
        self.running = True
        self.current_task: Optional[str] = None  # 正在處理的 URL
    
    def run(self):
        """工作執行緒主迴圈"""
        logger.info("下載工作執行緒已啟動")
        
        while self.running:
            try:
                # 從佇列取得任務（阻塞式等待，1秒超時）
                task = download_queue.get(timeout=1)
                
                if task is None:
                    continue
                
                # 支援格式: 
                # (url, channel_id)
                # (url, channel_id, status_msg_id)
                # (url, channel_id, status_msg_id, test_mode)
                # (url, channel_id, status_msg_id, test_mode, batch_id)
                batch_id = None
                if len(task) == 5:
                    url, channel_id, status_msg_id, test_mode, batch_id = task
                elif len(task) == 4:
                    url, channel_id, status_msg_id, test_mode = task
                elif len(task) == 3:
                    url, channel_id, status_msg_id = task
                    test_mode = False
                else:
                    url, channel_id = task
                    status_msg_id = None
                    test_mode = False
                
                self.current_task = url
                logger.info(f"處理下載任務: {url}")
                
                # 提取 gallery ID 並獲取頁數，發送開始訊息
                start_msg_id = None
                pages = 0
                title = ""
                media_id = ""
                current_gallery_id = None
                cancel_event = None
                match = re.search(r'/g/(\d+)', url)
                if match:
                    current_gallery_id = match.group(1)
                    gallery_id = current_gallery_id
                    
                    # 註冊取消事件
                    cancel_event = register_cancel_event(gallery_id)
                    
                    pages, title, media_id = get_nhentai_page_count(gallery_id)
                    if pages > 0:
                        # 發送開始下載訊息（包含頁數和預估時間），並返回訊息 ID
                        future = asyncio.run_coroutine_threadsafe(
                            self.send_start_message(channel_id, gallery_id, pages, title, media_id),
                            self.bot.loop
                        )
                        start_msg_id = future.result(timeout=10)
                
                # 檢查是否在開始前就被取消
                if current_gallery_id and is_cancelled(current_gallery_id):
                    logger.info(f"下載已取消 (開始前): {current_gallery_id}")
                    unregister_cancel_event(current_gallery_id)
                    self.current_task = None
                    download_queue.task_done()
                    continue
                
                # 創建下載處理器（傳入取消事件）
                processor = DownloadProcessor(url, total_pages=pages, cancel_event=cancel_event)
                
                # 啟動進度監控執行緒
                progress_stop_event = threading.Event()
                if start_msg_id and pages > 0:
                    progress_thread = threading.Thread(
                        target=self._monitor_progress,
                        args=(processor, channel_id, start_msg_id, pages, title, gallery_id, media_id, progress_stop_event),
                        daemon=True
                    )
                    progress_thread.start()
                
                # 執行下載處理
                success, message = processor.process()
                
                # 檢查是否被取消
                was_cancelled = current_gallery_id and is_cancelled(current_gallery_id)
                if was_cancelled:
                    success = False
                    message = f"🚫 下載已取消: #{current_gallery_id}"
                
                # 取消註冊取消事件
                if current_gallery_id:
                    unregister_cancel_event(current_gallery_id)
                
                # 停止進度監控
                progress_stop_event.set()
                
                # 更新開始下載訊息（顯示最終狀態）
                if start_msg_id and not was_cancelled:
                    asyncio.run_coroutine_threadsafe(
                        self.update_final_progress(channel_id, start_msg_id, success, pages, title, gallery_id),
                        self.bot.loop
                    )
                
                # 發送結果到 Discord (取消時不發送額外訊息)
                if not was_cancelled:
                    asyncio.run_coroutine_threadsafe(
                        self.send_result(channel_id, message),
                        self.bot.loop
                    )
                
                # 更新批次追蹤
                if batch_id:
                    batch_result = update_batch(batch_id, success, current_gallery_id)
                    if batch_result:
                        # 批次完成，發送總結
                        asyncio.run_coroutine_threadsafe(
                            self.send_batch_summary(batch_result),
                            self.bot.loop
                        )
                
                self.current_task = None
                download_queue.task_done()
            
            except Empty:
                # 佇列為空，這是正常的，繼續等待
                continue
                
            except Exception as e:
                self.current_task = None
                logger.exception(f"工作執行緒錯誤: {e}")
    
    def _monitor_progress(self, processor: DownloadProcessor, channel_id: int, 
                          message_id: int, total_pages: int, title: str, 
                          gallery_id: str, media_id: str, stop_event: threading.Event):
        """
        監控下載進度並更新 Discord 訊息
        
        在背景執行緒中定期檢查已下載的圖片數量，並編輯訊息顯示進度條
        """
        last_count = 0
        last_pdf_progress = -1
        start_time = time.time()
        pdf_start_time = None  # PDF 轉換開始時間
        first_image_sent = False  # 追蹤是否已發送第一張圖片
        pdf_mode = False  # 是否進入 PDF 模式
        
        while not stop_event.is_set():
            try:
                # 根據模式調整檢查間隔
                check_interval = 1 if pdf_mode else PROGRESS_UPDATE_INTERVAL
                
                # 等待一段時間
                if stop_event.wait(timeout=check_interval):
                    break  # 收到停止信號
                
                # 檢查是否在 PDF 轉換階段
                if processor.pdf_converting:
                    pdf_mode = True
                    pdf_progress = processor.pdf_progress
                    
                    # 記錄 PDF 開始時間
                    if pdf_start_time is None:
                        pdf_start_time = time.time()
                    
                    if pdf_progress != last_pdf_progress:
                        last_pdf_progress = pdf_progress
                        
                        # 計算 PDF 預估剩餘時間
                        pdf_eta_str = "計算中..."
                        if pdf_progress > 0:
                            pdf_elapsed = time.time() - pdf_start_time
                            pdf_eta_seconds = (pdf_elapsed / pdf_progress) * (100 - pdf_progress)
                            if pdf_eta_seconds >= 60:
                                pdf_eta_str = f"{int(pdf_eta_seconds // 60)}分{int(pdf_eta_seconds % 60)}秒"
                            else:
                                pdf_eta_str = f"{int(pdf_eta_seconds)}秒"
                        
                        # 顯示 PDF 轉換進度
                        pdf_bar = create_progress_bar(pdf_progress, 100)
                        # 下載進度條保持 100%
                        download_bar = create_progress_bar(total_pages, total_pages)
                        
                        asyncio.run_coroutine_threadsafe(
                            self.update_pdf_progress_message(
                                channel_id, message_id, 
                                pdf_progress, pdf_bar, download_bar, total_pages, title, pdf_eta_str
                            ),
                            self.bot.loop
                        )
                    continue
                
                # 獲取已下載數量
                current_count = processor.get_downloaded_count()
                
                # 等第 3 張圖片下載完成後，發送第一張圖片（確保第一張已完整下載）
                if current_count >= 3 and not first_image_sent:
                    first_image_sent = True
                    # 等待 1 秒確保 NAS 寫入完成
                    time.sleep(1)
                    first_image = processor.get_first_image_path()
                    # 確認檔案大小大於 0
                    if first_image and first_image.exists() and first_image.stat().st_size > 0:
                        asyncio.run_coroutine_threadsafe(
                            self.send_cover_image(channel_id, first_image),
                            self.bot.loop
                        )
                
                # 下載完成時，切換到更頻繁的檢查模式以偵測 PDF 轉換
                if current_count >= total_pages:
                    pdf_mode = True
                
                # 只有進度有變化時才更新
                if current_count != last_count and current_count > 0:
                    last_count = current_count
                    
                    # 計算進度和預估剩餘時間
                    progress_bar = create_progress_bar(current_count, total_pages)
                    elapsed = time.time() - start_time
                    
                    if current_count > 0:
                        avg_time_per_page = elapsed / current_count
                        remaining_pages = total_pages - current_count
                        eta_seconds = remaining_pages * avg_time_per_page
                        
                        if eta_seconds >= 60:
                            eta_str = f"{int(eta_seconds // 60)}分{int(eta_seconds % 60)}秒"
                        else:
                            eta_str = f"{int(eta_seconds)}秒"
                    else:
                        eta_str = "計算中..."
                    
                    # 更新訊息
                    asyncio.run_coroutine_threadsafe(
                        self.update_progress_message(
                            channel_id, message_id, 
                            current_count, total_pages, 
                            progress_bar, eta_str, title
                        ),
                        self.bot.loop
                    )
                    
            except Exception as e:
                logger.error(f"進度監控錯誤: {e}")
    
    async def send_cover_image(self, channel_id: int, image_path: Path):
        """發送封面圖片作為附件"""
        try:
            channel = self.bot.get_channel(channel_id)
            if channel and image_path and image_path.exists():
                await channel.send(file=discord.File(image_path))
                logger.info(f"已發送封面圖片: {image_path.name}")
        except Exception as e:
            logger.error(f"發送封面圖片失敗: {e}")
    
    async def update_progress_message(self, channel_id: int, message_id: int,
                                       current: int, total: int,
                                       progress_bar: str, eta: str, title: str):
        """編輯訊息更新下載進度"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                return
            
            # 編輯訊息
            new_content = (
                f"🔄 下載中...\n"
                f"📖 {title}\n"
                f"{progress_bar}\n"
                f"({current}/{total}) ⏱️ 預估剩餘: {eta}"
            )
            await message.edit(content=new_content)
            
        except Exception as e:
            logger.error(f"更新進度訊息失敗: {e}")
    
    async def update_pdf_progress_message(self, channel_id: int, message_id: int,
                                          progress: int, pdf_bar: str, download_bar: str, 
                                          total_pages: int, title: str, eta: str = ""):
        """編輯訊息更新 PDF 轉換進度"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                return
            
            # 編輯訊息 - 顯示兩條進度條
            new_content = (
                f"📄 製作 PDF 中...\n"
                f"📖 {title}\n"
                f"下載: \n{download_bar}\n"
                f"({total_pages}/{total_pages})\n"
                f"PDF: \n{pdf_bar}\n"
                f"⏱️ 預估剩餘: {eta}"
            )
            await message.edit(content=new_content)
            
        except Exception as e:
            logger.error(f"更新 PDF 進度訊息失敗: {e}")
    
    async def update_final_progress(self, channel_id: int, message_id: int, 
                                    success: bool, total: int, title: str, gallery_id: str = ""):
        """更新最終進度狀態"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                return
            
            # 更新訊息內容和表情
            if success:
                progress_bar = create_progress_bar(total, total)
                
                # 建立下載完成互動視圖
                from bot.views import DownloadCompleteView
                view = DownloadCompleteView(
                    gallery_id=gallery_id if gallery_id else "unknown",
                    title=title
                )
                
                await message.edit(
                    content=f"✅ 下載完成\n📖 {title}\n{progress_bar}\n({total}/{total})",
                    view=view
                )
                await message.add_reaction('✅')
            else:
                await message.add_reaction('❌')
            
        except Exception as e:
            logger.error(f"更新最終進度失敗: {e}")
    
    async def send_start_message(self, channel_id: int, gallery_id: str, pages: int, title: str, media_id: str = "") -> int:
        """
        發送開始下載訊息（包含頁數和預估時間 + 取消按鈕）
        
        Returns:
            訊息 ID，失敗時返回 None
        """
        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                # 計算預估時間
                est_seconds = pages * SECONDS_PER_PAGE
                if est_seconds >= 60:
                    est_str = f"{int(est_seconds // 60)}分{int(est_seconds % 60)}秒"
                else:
                    est_str = f"{int(est_seconds)}秒"
                
                # 初始進度條
                progress_bar = create_progress_bar(0, pages)
                
                # 建立帶有取消按鈕的 View
                from bot.views import DownloadProgressView
                view = DownloadProgressView(gallery_id=gallery_id, title=title)
                
                # 發送進度訊息
                msg = await channel.send(
                    f"🔄 開始下載 **#{gallery_id}**\n"
                    f"📖 {title}\n"
                    f"{progress_bar}\n"
                    f"(0/{pages}) ⏱️ 預估: {est_str}",
                    view=view
                )
                
                return msg.id
        except Exception as e:
            logger.error(f"發送開始訊息失敗: {e}")
        return None
    
    async def update_status_reaction(self, channel_id: int, message_id: int, success: bool):
        """更新狀態訊息的表情：添加 ✅ 或 ❌（已不再使用，保留兼容性）"""
        if not message_id:
            return
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return
            
            message = await channel.fetch_message(message_id)
            if not message:
                return
            
            # 添加結果表情
            result_emoji = '✅' if success else '❌'
            await message.add_reaction(result_emoji)
            
        except Exception as e:
            logger.error(f"更新狀態表情失敗: {e}")
    
    async def send_result(self, channel_id: int, message: str):
        """發送結果訊息到 Discord 頻道"""
        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(message)
        except Exception as e:
            logger.error(f"發送訊息失敗: {e}")
    
    async def send_batch_summary(self, batch_result: Dict[str, Any]):
        """發送批次下載完成總結"""
        try:
            channel = self.bot.get_channel(batch_result['channel_id'])
            if not channel:
                return
            
            total = batch_result['total']
            success = batch_result['success']
            failed = batch_result['failed']
            
            # 構建總結訊息
            if failed == 0:
                emoji = "🎉"
                status = "全部成功"
            elif success == 0:
                emoji = "❌"
                status = "全部失敗"
            else:
                emoji = "⚠️"
                status = "部分完成"
            
            msg_lines = [
                f"{emoji} **批次下載完成** - {status}",
                f"",
                f"📊 **統計結果**",
                f"• 總計: {total} 個",
                f"• ✅ 成功: {success} 個",
                f"• ❌ 失敗: {failed} 個",
            ]
            
            # 如果有失敗的，列出失敗的 ID
            if batch_result.get('failed_ids'):
                failed_ids = batch_result['failed_ids'][:10]  # 最多顯示 10 個
                failed_list = ", ".join([f"`{gid}`" for gid in failed_ids])
                msg_lines.append(f"")
                msg_lines.append(f"❌ 失敗清單: {failed_list}")
                if len(batch_result['failed_ids']) > 10:
                    msg_lines.append(f"... 及其他 {len(batch_result['failed_ids']) - 10} 個")
            
            await channel.send("\n".join(msg_lines))
            logger.info(f"批次下載完成: {success}/{total} 成功")
            
        except Exception as e:
            logger.error(f"發送批次總結失敗: {e}")
    
    def stop(self):
        """停止工作執行緒"""
        self.running = False
