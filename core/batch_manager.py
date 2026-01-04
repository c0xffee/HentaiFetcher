#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher Batch Manager
===========================
批次下載管理與取消機制
"""

import threading
from queue import Queue
from datetime import datetime
from typing import Dict, Any, List, Optional


# 下載佇列 - 結構: (url, channel_id, status_message_id, force_mode, batch_id)
download_queue: Queue = Queue()

# 取消下載追蹤器 - 用於標記需要取消的下載任務
# 結構: {gallery_id: threading.Event}  - Event 被 set 時表示任務應該被取消
cancel_events: Dict[str, threading.Event] = {}
cancel_lock = threading.Lock()

# 批次下載追蹤器 - 用於統計多檔案下載結果
# 結構: {batch_id: {'total': int, 'success': int, 'failed': int, 'channel_id': int, 'gallery_ids': List[str]}}
batch_tracker: Dict[str, Dict[str, Any]] = {}
batch_lock = threading.Lock()

# 訊息去重（避免重複處理同一訊息）
processed_messages: set = set()


def request_cancel(gallery_id: str) -> bool:
    """請求取消下載"""
    with cancel_lock:
        if gallery_id in cancel_events:
            cancel_events[gallery_id].set()
            return True
        return False


def register_cancel_event(gallery_id: str) -> threading.Event:
    """註冊取消事件"""
    with cancel_lock:
        event = threading.Event()
        cancel_events[gallery_id] = event
        return event


def unregister_cancel_event(gallery_id: str):
    """取消註冊取消事件"""
    with cancel_lock:
        cancel_events.pop(gallery_id, None)


def is_cancelled(gallery_id: str) -> bool:
    """檢查是否已被取消"""
    with cancel_lock:
        event = cancel_events.get(gallery_id)
        return event.is_set() if event else False


def generate_batch_id() -> str:
    """生成批次 ID"""
    return f"B{int(datetime.now().timestamp() * 1000)}"


def init_batch(batch_id: str, total: int, channel_id: int, gallery_ids: List[str]):
    """初始化批次追蹤"""
    with batch_lock:
        batch_tracker[batch_id] = {
            'total': total,
            'success': 0,
            'failed': 0,
            'channel_id': channel_id,
            'gallery_ids': gallery_ids,
            'completed_ids': [],
            'failed_ids': []
        }


def update_batch(batch_id: str, success: bool, gallery_id: str = None) -> Optional[Dict[str, Any]]:
    """
    更新批次狀態，如果完成則返回統計結果
    
    Returns:
        如果批次完成，返回統計資訊；否則返回 None
    """
    with batch_lock:
        if batch_id not in batch_tracker:
            return None
        
        batch = batch_tracker[batch_id]
        if success:
            batch['success'] += 1
            if gallery_id:
                batch['completed_ids'].append(gallery_id)
        else:
            batch['failed'] += 1
            if gallery_id:
                batch['failed_ids'].append(gallery_id)
        
        # 檢查是否完成
        if batch['success'] + batch['failed'] >= batch['total']:
            result = batch.copy()
            del batch_tracker[batch_id]
            return result
        
        return None


def is_message_processed(message_id: int, max_messages: int = 1000) -> bool:
    """
    檢查訊息是否已處理過
    
    Args:
        message_id: 訊息 ID
        max_messages: 最多保留的記錄數
    
    Returns:
        是否已處理過
    """
    global processed_messages
    if message_id in processed_messages:
        return True
    
    # 清理過舊的記錄
    if len(processed_messages) >= max_messages:
        # 清除一半的記錄
        processed_messages = set(list(processed_messages)[max_messages // 2:])
    
    processed_messages.add(message_id)
    return False


def get_queue_size() -> int:
    """獲取當前佇列大小"""
    return download_queue.qsize()


def add_to_queue(url: str, channel_id: int, status_message_id: int, force_mode: bool, batch_id: str = None):
    """
    加入下載佇列
    
    Args:
        url: 下載 URL
        channel_id: Discord 頻道 ID
        status_message_id: 狀態訊息 ID
        force_mode: 是否強制下載
        batch_id: 批次 ID（可選）
    """
    download_queue.put((url, channel_id, status_message_id, force_mode, batch_id))
