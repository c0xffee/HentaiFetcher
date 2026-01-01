# Tech Context

## Technology Stack

### Runtime
- **Language**: Python 3.9+
- **Platform**: Docker Container on Synology NAS

### Core Dependencies
| 套件 | 版本 | 用途 |
|------|------|------|
| discord.py | 2.x | Discord Bot 框架 |
| gallery-dl | latest | 漫畫網站下載器 |
| img2pdf | latest | 無損 PDF 轉換 |
| Pillow | latest | 圖片處理 |
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

## Development Environment
- **IDE**: VS Code + GitHub Copilot
- **Local Testing**: 使用 `.env` 載入 Token
- **Production**: Docker Container

## Known Limitations (已知限制)
- [待填入]

## Future Considerations (未來考量)
- [待訪談確認]
