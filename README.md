# 🎌 HentaiFetcher

> 在 Synology NAS 上透過 Discord Bot 自動化漫畫下載、PDF 轉換以及 Eagle Metadata 生成

**版本**: v3.4.0 (模組化架構)  
**分支**: `refactor/modularize-run-py`

## 📋 功能特色

- 🤖 **Discord Slash Commands** - 使用 `/dl`, `/search`, `/read` 等斜線指令
- 📥 **gallery-dl 核心** - 支援多個漫畫網站 (nhentai, e-hentai, hitomi 等)
- 📄 **等寬 PDF 轉換** - 使用 Pillow 製作等寬 PDF，pikepdf 線性化加速網頁瀏覽
- 🦅 **Eagle 雙向整合** - 自動生成 metadata.json + Eagle Plugin 自動匯入
- 🎮 **互動式 UI** - Select Menu、Button、分頁瀏覽等 Discord UI 元件
- 🔍 **智慧搜尋** - 支援 Eagle Library + downloads 雙來源搜尋
- 🧹 **自動清理** - 轉換完成後自動刪除原始圖片節省空間
- 🐳 **Docker 容器化** - 一鍵部署，無需額外設定
- 📦 **模組化架構** - v3.4.0 重構為 core/, utils/, services/, bot/commands/ 結構

## 🚀 快速開始

### 1. 取得 Discord Bot Token

1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)
2. 點擊 **New Application**，輸入名稱 (例如: HentaiFetcher)
3. 進入 **Bot** 頁籤，點擊 **Add Bot**
4. 在 **Token** 區塊點擊 **Reset Token**，複製並保存
5. 開啟 **MESSAGE CONTENT INTENT** (必要！)
6. 進入 **OAuth2 → URL Generator**：
   - Scopes: 勾選 `bot`
   - Bot Permissions: 勾選 `Send Messages`, `Read Message History`
7. 複製產生的 URL，在瀏覽器開啟並邀請 Bot 到你的伺服器

### 2. 在 Synology NAS 上部署

#### 方法 A: 使用 SSH

```bash
# 連接到 NAS
ssh admin@your-nas-ip

# 建立專案目錄
mkdir -p /volume1/docker/HentaiFetcher
cd /volume1/docker/HentaiFetcher

# 建立必要子目錄
mkdir -p config downloads temp

# 上傳或建立檔案 (run.py, Dockerfile, docker-compose.yml)

# 設定 Token
echo "DISCORD_TOKEN=你的Bot_Token" > .env

# 建構並啟動
docker-compose up -d --build
```

#### 方法 B: 使用 Synology Docker 套件

1. 開啟 **File Station**，建立資料夾結構:
   ```
   /docker/HentaiFetcher/
   ├── config/
   ├── downloads/
   ├── temp/
   ├── run.py
   ├── Dockerfile
   └── docker-compose.yml
   ```

2. 開啟 **Container Manager** (或 Docker 套件)

3. 前往 **專案** → **新增** → 選擇 `docker-compose.yml` 所在資料夾

4. 設定環境變數 `DISCORD_TOKEN`

5. 建置並啟動

### 3. 驗證部署

在 Discord 中發送：
```
/ping
```
Bot 應回覆 `🏓 Pong! 延遲: XXms`

## 📖 使用指南

### 斜線指令 (Slash Commands)

#### 下載相關
| 指令 | 說明 | 範例 |
|------|------|------|
| `/dl <gallery_ids>` | 下載漫畫 (支援多個 ID) | `/dl 421633` |
| `/queue` | 查看佇列狀態 | `/queue` |

#### 庫管理
| 指令 | 說明 | 範例 |
|------|------|------|
| `/list` | 列出所有已下載的本子 (分頁) | `/list` |
| `/random [count] [source]` | 隨機顯示 (1-5本) | `/random 3 eagle` |
| `/search <query> [source]` | 搜尋本子 | `/search gyaru` |
| `/read <nhentai_id>` | 取得 PDF 連結和詳細資訊 | `/read 421633` |
| `/fixcover` | 為已下載的本子補充封面 | `/fixcover` |
| `/cleanup` | 清除 imported 中已入庫項目 | `/cleanup` |

#### Eagle 相關
| 指令 | 說明 | 範例 |
|------|------|------|
| `/eagle` | 顯示 Eagle Library 統計 | `/eagle` |
| `/reindex` | 重建 Eagle Library 索引 | `/reindex` |

#### 系統資訊
| 指令 | 說明 | 範例 |
|------|------|------|
| `/ping` | 測試 Bot 連線 | `/ping` |
| `/version` | 顯示 Bot 版本 | `/version` |
| `/status` | 顯示 Bot 狀態 | `/status` |
| `/help` | 顯示使用說明 | `/help` |
| `/sync` | 同步斜線指令 (管理員) | `/sync` |

### 專用頻道模式

在名為 `hentaifetcher`, `hentai-fetcher` 或 `nhentai` 的頻道中：
- **直接貼號碼或網址即可下載** (不需要 `/dl`)
- 支援批次下載：`421633 607769 613358`
- 強制重新下載：`test 421633`

### 輸出結構

每次下載完成後，會在 `downloads/` 目錄生成：

```
downloads/
└── [Gallery_ID]/
    ├── [Gallery_ID].pdf   # 線性化 PDF (Fast Web View)
    ├── cover.jpg          # 封面圖片
    └── metadata.json      # Eagle 相容 metadata
```

### Eagle Metadata 格式

```json
{
    "id": "L1703849123456",
    "name": "漫畫標題",
    "url": "https://nhentai.net/g/123456/",
    "tags": ["tag1", "parody:xxx", "artist:yyy"],
    "annotation": "Downloaded via HentaiFetcher Bot"
}
```

## ⚙️ 進階設定

### gallery-dl 配置

編輯 `config/gallery-dl.conf` 可自訂下載行為：

```json
{
    "extractor": {
        "nhentai": {
            "username": "your_username",
            "password": "your_password"
        },
        "exhentai": {
            "username": "your_username",
            "password": "your_password"
        }
    }
}
```

### 資源限制

在 `docker-compose.yml` 中取消註解以限制資源使用：

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
```

### 日誌查看

```bash
# 即時查看日誌
docker-compose logs -f

# 查看 Bot 日誌檔
cat config/bot.log
```

## 🛠️ 故障排除

### Bot 無法登入

1. 確認 Token 正確無誤
2. 確認 Token 沒有過期 (重新生成)
3. 檢查 `.env` 檔案格式

### 下載失敗

1. 確認網址格式正確
2. 檢查 gallery-dl 是否支援該網站
3. 查看日誌獲取詳細錯誤

### 權限問題

```bash
# 修正權限
chmod -R 777 config downloads temp
```

## 📁 目錄結構

```
HentaiFetcher/
├── run.py              # 啟動器 (~80 lines)
├── core/               # 核心模組
│   ├── config.py       # 配置、路徑、常數、Logger
│   ├── batch_manager.py # 佇列管理、批次追蹤
│   ├── download_processor.py # 下載處理邏輯
│   └── download_worker.py    # 背景下載 Worker
├── utils/              # 工具函式
│   ├── helpers.py      # 純工具函式 (sanitize, progress_bar)
│   └── url_parser.py   # URL 解析
├── services/           # 服務層
│   ├── nhentai_api.py  # nhentai API 互動
│   ├── metadata_service.py # Metadata 解析與生成
│   └── index_service.py    # 索引管理與搜尋
├── bot/                # Discord Bot 模組
│   ├── bot.py          # HentaiFetcherBot 類別
│   ├── commands/       # 斜線指令
│   │   ├── download.py # /dl, /queue
│   │   ├── info.py     # /ping, /version, /status, /help
│   │   ├── library.py  # /list, /random, /search, /read...
│   │   └── admin.py    # /sync
│   └── views/          # Discord UI 元件
│       ├── search_view.py
│       ├── read_view.py
│       ├── random_view.py
│       └── ...
├── eagle_library.py    # Eagle Library 操作模組
├── Dockerfile          # Docker 映像定義
├── docker-compose.yml  # Docker Compose 配置
├── .env                # 環境變數 (需自行建立)
├── config/             # 配置目錄
│   ├── gallery-dl.conf # gallery-dl 設定
│   └── bot.log         # Bot 日誌
├── downloads/          # 最終輸出 (PDF + metadata)
├── imported/           # Eagle 已匯入項目歸檔
├── temp/               # 暫存目錄 (自動清理)
├── memory-bank/        # 專案文件 (Vibe Coding)
└── nHentai-Auto-Importer/ # Eagle NAS 自動入庫插件
```

## 🔧 技術細節

- **版本**: v3.4.0 (模組化重構版)
- **架構**: 從 3834 行單文件重構為模組化架構
- **基礎映像**: `python:3.9-slim`
- **主要依賴**:
  - `discord.py` >= 2.3.0 (Slash Commands)
  - `gallery-dl` >= 1.26.0
  - `pikepdf` >= 8.0.0 (PDF 線性化)
  - `Pillow` >= 10.0.0 (圖片處理 + PDF 生成)
  - `requests` >= 2.31.0

### 架構演進
- **v3.3.x**: 單一 run.py (3834 行, God Object)
- **v3.4.0**: 模組化架構 (core/, utils/, services/, bot/commands/)

## ⚠️ 免責聲明

本工具僅供個人學習與研究使用。請遵守當地法律法規，尊重版權。使用者需自行承擔使用本工具的一切法律責任。

## 📄 授權

MIT License

---

**Made with ❤️ for Synology NAS users**
