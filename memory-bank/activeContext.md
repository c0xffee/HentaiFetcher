# Active Context

## Current Focus (目前焦點)
- 斜線指令版本 v3.0.0 完成

## Recent Changes (最近更動)
- [x] 2026-01-02 清理 on_message 處理邏輯
  - 移除舊的 `known_commands` 轉換邏輯
  - 移除 `!dl` 和 `!test` 傳統指令處理
  - 專用頻道：忽略 `/` 開頭訊息（由 Discord 處理）
  - 非專用頻道：提示使用斜線指令
- [x] 2026-01-02 升級為斜線指令版本 (v3.0.0)
  - 所有指令改為 Discord 斜線指令 (/dl, /search, /read 等)
  - 專用頻道仍支援直接貼號碼下載 + test 模式
- [x] 2026-01-02 修復 Docker 容器 Eagle Library 路徑
  - `eagle_library.py` 自動偵測 Docker 環境
  - Docker 使用 `/app/eagle-library` 和 `/app/imports-index.json`
- [x] 2026-01-02 新增重複下載檢查功能
  - `/dl` 指令加入 `force` 參數強制重新下載

## Next Steps (下一步)
- [ ] 重新部署 Docker 並測試斜線指令
- [ ] 測試完整下載 → PDF 生成流程

## Notes (備註)
- 專案版本：v3.0.0
- 主要程式：run.py
