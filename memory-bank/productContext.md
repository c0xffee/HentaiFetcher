# Product Context

## Core Problem (核心問題)
- 在 Synology NAS 上自動化漫畫收藏流程
- 透過 Discord 指令觸發下載，無需登入 NAS
- 自動轉換為 PDF 並生成 Eagle 相容的 metadata

## User Persona (目標用戶)
- **個人收藏家**：希望在手機/電腦上透過 Discord 快速收藏漫畫到 NAS
- **Eagle 使用者**：需要統一的 metadata 格式以便管理收藏

## Success Metrics (成功定義)
- MVP 關鍵功能：
  - [x] Discord Bot 接收 `!dl <url>` 指令
  - [x] 支援 nhentai、e-hentai、hitomi 等網站
  - [x] 自動下載並轉換為 PDF
  - [x] 生成 Eagle 相容的 metadata.json
  - [x] 自動清理原始圖片節省空間
  - [ ] [待訪談確認更多功能]

## 🛑 Anti-Scope (不做什麼)
- [ ] [待訪談確認]
- [ ] 例如：不處理付費內容
- [ ] 例如：不做 Web UI
