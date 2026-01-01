# Active Context

## Current Focus (目前焦點)
- 正在執行的任務：修復 PDF 圖片寬度不一致問題

## Recent Changes (最近更動)
- [x] 2026-01-02 改進 fixcover 指令
  - 當 nhentai 封面下載失敗時，自動使用第一張圖片作為封面
  - 新增 `get_first_image_as_cover` 函數
- [x] 2026-01-02 移除重複跳過功能 + 修復 PDF 連結
  - 移除「已存在就跳過」的邏輯，改為時間戳命名
  - 修復連結使用實際資料夾名稱（含編號）
  - 移除 skip_duplicate_check 參數
- [x] 2026-01-02 修復 PDF 等寬問題 (fix/pdf-equal-width)
  - 改用 Pillow 取代 img2pdf 進行 PDF 轉換
  - 自動找出最大寬度，將所有圖片按比例縮放
  - 確保 PDF 每頁都是 100% 寬度對齊
  - 支援 RGBA/P/LA 等模式轉換為 RGB
- [x] 2026-01-02 建立 Vibe Coding 文件架構
  - 建立 `.github/copilot-instructions.md`
  - 建立 `raw-context.md`
  - 建立 `project-brief.md`
  - 建立 `memory-bank/` 資料夾及 5 個標準檔案
- [x] 2026-01-02 加強自動更新規則
  - 新增 `MANDATORY AUTO-UPDATE PROTOCOL` 到 copilot-instructions.md
  - 強化 systemPatterns.md 的 AI 行為準則
  - AI 現在必須自動更新 Memory Bank + Git Commit
  - 同步更新 VIBE_WORKFLOW_MASTER.md 讓其他專案也能使用

## Next Steps (下一步)
- [ ] 測試 PDF 等寬功能
- [ ] 進行顧問式訪談，收斂需求
- [ ] 完善 productContext.md 的功能範疇

## Open Questions (待解決問題)
- [ ] 是否有新功能需求？
- [ ] 是否需要重構現有程式碼？
- [ ] 測試策略如何規劃？

## Notes (備註)
- 專案版本：v2.8.0
- 主要程式：run.py (約 2800 行)
