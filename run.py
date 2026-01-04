#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher - Discord Bot 自動化漫畫下載器
==============================================

版本: 3.4.0 - 模組化重構版本

功能：
1. Discord Bot 使用斜線指令 (/dl, /search, /read 等)
2. 使用 gallery-dl 下載圖片與 metadata
3. 使用 Pillow 轉換為等寬 PDF
4. 生成 Eagle 相容的 metadata.json
5. 自動清理原始圖片檔案
6. 整合 Eagle Library 查詢

架構：
- core/          核心模組 (config, batch_manager, download_processor, download_worker)
- utils/         工具函式 (helpers, url_parser)
- services/      服務層 (nhentai_api, metadata_service, index_service)
- bot/           Discord Bot 模組 (bot, commands/, views/)
"""

import os
import sys

# 版本號 - 用來確認容器是否更新
from core.config import VERSION, logger

print(f"[STARTUP] HentaiFetcher 版本 {VERSION} 正在載入...", flush=True)

# 載入 .env 檔案（本地測試用）
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("[STARTUP] 已載入 .env 檔案", flush=True)
except ImportError:
    pass  # Docker 環境不需要 dotenv

# 導入 Discord Bot
import discord
from bot import HentaiFetcherBot
from bot.commands import setup_commands

print(f"[STARTUP] 模組載入完成", flush=True)


def main():
    """主程式入口"""
    # 取得 Discord Token
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        logger.error("錯誤: 未設定 DISCORD_TOKEN 環境變數")
        logger.error("請在 docker-compose.yml 中設定 DISCORD_TOKEN")
        sys.exit(1)
    
    # 建立 Bot 實例
    bot = HentaiFetcherBot()
    
    # 設定斜線指令
    setup_commands(bot)
    
    try:
        logger.info("正在啟動 HentaiFetcher Bot...")
        bot.run(token)
    except discord.LoginFailure:
        logger.error("Discord 登入失敗: Token 無效")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Bot 執行錯誤: {e}")
        sys.exit(1)
    finally:
        # 停止工作執行緒
        if bot.worker:
            bot.worker.stop()


if __name__ == '__main__':
    main()
