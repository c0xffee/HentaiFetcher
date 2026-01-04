# Tech Context

## Technology Stack

### Runtime
- **Language**: Python 3.9+
- **Platform**: Docker Container on Synology NAS

### Core Dependencies
| 套件 | 版本 | 用途 |
|------|------|------|
| discord.py | 2.x | Discord Bot 框架 (Slash Commands) |
| gallery-dl | latest | 漫畫網站下載器 |
| pikepdf | latest | PDF 線性化 (Fast Web View) |
| Pillow | latest | 圖片處理 + PDF 生成 |
| requests | latest | HTTP 請求 |
| python-dotenv | latest | 環境變數載入 (開發用) |

### Infrastructure
- **Container**: Docker + Docker Compose
- **Host**: Synology NAS (DSM 7.x)
- **Storage**: NAS Volume (/volume1/docker/HentaiFetcher/)

## Environment Variables
| 變數名稱 | 用途 | 必填 |
|----------|------|------|
| DISCORD_TOKEN | Discord Bot Token | ✅ |

## Supported Sites (gallery-dl)
- nhentai.net
- e-hentai.org
- hitomi.la
- [其他 gallery-dl 支援的網站]

## External Integrations
- **Discord API**: Bot 指令與訊息互動
- **Eagle**: 透過 metadata.json 匯入收藏
- **Eagle Plugin API**: 背景服務自動匯入 PDF 與 metadata

## Eagle Auto-Importer 插件
- **類型**: Background Service
- **執行環境**: Eagle Plugin API (基於 Node.js)
- **監控路徑**: `Z:\HentaiFetcher\downloads` (映射磁碟機)
- **歸檔路徑**: `Z:\HentaiFetcher\imported`
- **索引檔案**: `Z:\HentaiFetcher\imports-index.json`
- **掃描間隔**: 30 秒
- **注意**: Eagle API 不支援 UNC 路徑，必須使用映射磁碟機

## Development Environment
- **IDE**: VS Code + GitHub Copilot
- **Local Testing**: 使用 `.env` 載入 Token
- **Production**: Docker Container

## Known Limitations (已知限制)
- **Discord 文字無法變成按鈕**：訊息內的標籤文字無法直接點擊執行指令
- **解決方案**：使用 Select Menu 下拉選單選擇 Tag 進行搜尋

## Discord UI 元件規劃
> 使用 discord.py 2.x 的 View/Button/Select 元件

### 持久化設計
- **Persistent Views**：Bot 重啟後按鈕仍可運作
- **custom_id 格式**：`{action}:{data}` (例如 `read:432205`, `tag_search:gyaru`)
- **超時時間**：5 分鐘後自動禁用

### View 類別架構
| View 類別 | 元件類型 | 功能 |
|-----------|----------|------|
| `SearchResultView` | Select Menu + Button | 搜尋結果選擇 → 執行 `/read` |
| `ReadDetailView` | Button + Select Menu | 詳情頁操作 + Tag 選擇搜尋 |
| `RandomResultView` | Button | 隨機結果操作 |
| `DownloadCompleteView` | Button | 下載完成後操作 |
| `PaginatedListView` | Button | 分頁瀏覽 (可選) |

### custom_id 命名規範
```
read:{nhentai_id}         # 查看詳情
dl:{nhentai_id}           # 下載
tag_search:{tag_name}     # 搜尋同標籤
artist_search:{artist}    # 搜尋同作者
parody_search:{parody}    # 搜尋同原作
random:1                  # 再抽一次
open_pdf:{nhentai_id}     # 開啟 PDF (Link Button)
```

## Project Structure (專案結構)
> v3.4.0 模組化架構

```
HentaiFetcher/
├── run.py              # 啟動器 (~80 lines)
├── core/               # 核心模組
│   ├── config.py       # 配置、路徑、常數、Logger
│   ├── batch_manager.py # 佇列管理、批次追蹤
│   ├── download_processor.py # 下載處理邏輯
│   └── download_worker.py    # 背景下載 Worker
├── utils/              # 工具函式
│   ├── helpers.py      # 純工具函式
│   └── url_parser.py   # URL 解析
├── services/           # 服務層
│   ├── nhentai_api.py  # nhentai API
│   ├── metadata_service.py # Metadata 服務
│   └── index_service.py    # 索引與搜尋
├── bot/                # Discord Bot
│   ├── bot.py          # HentaiFetcherBot 類別
│   ├── commands/       # 斜線指令模組
│   │   ├── download.py # /dl, /queue
│   │   ├── info.py     # /ping, /version, /status, /help
│   │   ├── library.py  # /list, /random, /search, /read...
│   │   └── admin.py    # /sync
│   └── views/          # Discord UI 元件
│       ├── base.py
│       ├── search_view.py
│       ├── read_view.py
│       ├── random_view.py
│       ├── download_view.py
│       ├── list_view.py
│       ├── cleanup_view.py
│       └── helpers.py
├── eagle_library.py    # Eagle Library 操作
└── memory-bank/        # 專案文件
```

## Future Considerations (未來考量)
- [ ] 更多互動元件整合
- [ ] Modal 對話框 (例如批次下載輸入)
