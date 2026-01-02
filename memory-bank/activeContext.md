# Active Context

## Current Focus (目前焦點)
- 正在執行的任務：升級到斜線指令版本 + 修復 Docker 路徑問題

## Recent Changes (最近更動)
- [x] 2026-01-02 升級為斜線指令版本 (v3.0.0)
  - 所有指令改為 Discord 斜線指令 (/dl, /search, /read 等)
  - 移除傳統 ! 前綴指令
  - 專用頻道仍支援直接貼號碼下載
- [x] 2026-01-02 修復 Docker 容器 Eagle Library 路徑
  - `eagle_library.py` 自動偵測 Docker 環境
  - Docker 使用 `/app/eagle-library` 和 `/app/imports-index.json`
  - 本地使用 UNC 路徑
  - `docker-compose.yml` 新增 Eagle Library volume 掛載
- [x] 2026-01-02 新增重複下載檢查功能
  - 新增 `check_already_downloaded()` 函數
  - `/dl` 指令加入 `force` 參數強制重新下載
- [x] 2026-01-02 修復 metadata 寫入和插件空值檢查
- [x] 2026-01-02 新增 !reindex 指令
  - 新增 `@bot.command(name='reindex')` 指令重建索引
  - 支援 aliases: rebuild, sync
- [x] 2026-01-02 建立 eagle_library.py 模組
  - EagleLibrary 類別查詢 Eagle Library
  - 新增 `get_random()` 方法支援隨機抽選
- [x] 2026-01-02 修復 random 指令使用 Eagle Library
  - 改從 Eagle Library 索引隨機抽選
  - 封面圖片優先顯示

## Next Steps (下一步)
- [ ] 測試完整下載 → PDF 生成流程
- [ ] 確認 PDF 可正常匯入 Eagle Library

## Open Questions (待解決問題)
- [ ] PDF 生成失敗的具體原因待確認

## Notes (備註)
- 專案版本：v2.8.1
- 主要程式：run.py (約 3150 行)
