#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher Configuration
===========================
全域設定、路徑、常數與 Logger 配置
"""

import os
import sys
import logging
import platform
from pathlib import Path

# ==================== 版本號 ====================
VERSION = "3.5.0"

# ==================== 環境偵測 ====================
IS_DOCKER = platform.system() == 'Linux' and os.path.exists('/app')

if IS_DOCKER:
    # Docker 環境 - 使用容器內路徑
    BASE_DIR = Path('/app')
else:
    # 本地測試環境 - 使用專案資料夾
    BASE_DIR = Path(__file__).parent.parent.resolve()

# ==================== 資料夾路徑 ====================
CONFIG_DIR = BASE_DIR / 'config'
DOWNLOAD_DIR = BASE_DIR / 'downloads'
TEMP_DIR = BASE_DIR / 'temp'
IMPORTED_DIR = BASE_DIR / 'imported'

# 確保目錄存在
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
IMPORTED_DIR.mkdir(parents=True, exist_ok=True)

# ==================== 日誌設定 ====================
log_file = CONFIG_DIR / 'bot.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), encoding='utf-8')
    ]
)
logger = logging.getLogger('HentaiFetcher')

# ==================== 進度條設定 ====================
PROGRESS_UPDATE_INTERVAL = 3  # 每 3 秒更新一次進度
SECONDS_PER_PAGE = 3.6  # 預估每頁下載時間（實測平均值）
PROGRESS_BAR_WIDTH = 15  # 進度條寬度（格數）

# ==================== PDF Web 存取設定 ====================
PDF_WEB_BASE_URL = "https://com1c.c0xffee.com"  # Web Station 基礎 URL (downloads)

# ==================== 專用頻道設定 ====================
# 在這些頻道中不需要 !dl 前綴
DEDICATED_CHANNEL_NAMES = ['hentaifetcher', 'hentai-fetcher', 'nhentai']  # 頻道名稱
DEDICATED_CHANNEL_IDS = []  # 或直接設定頻道 ID

# ==================== 訊息去重設定 ====================
MAX_PROCESSED_MESSAGES = 1000  # 最多保留 1000 筆記錄

# ==================== 索引設定 ====================
REINDEX_COOLDOWN = 60  # 60 秒內不重複 reindex

# ==================== 啟動訊息 ====================
def print_startup_info():
    """印出啟動資訊"""
    print(f"[STARTUP] HentaiFetcher 版本 {VERSION} 正在載入...", flush=True)
    if IS_DOCKER:
        print("[STARTUP] 運行環境: Docker", flush=True)
    else:
        print(f"[STARTUP] 運行環境: 本地 ({BASE_DIR})", flush=True)
