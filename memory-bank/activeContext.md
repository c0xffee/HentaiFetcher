# Active Context

## Current Focus (目前焦點)
- 正在執行的任務：修復下載與 PDF 生成流程

## Recent Changes (最近更動)
- [x] 2026-01-02 新增重複下載檢查功能
  - 新增 `check_already_downloaded()` 函數查詢 Eagle Library
  - `!dl` 指令加入重複檢查，跳過已存在項目
  - 專用頻道直接貼號碼也會檢查重複
  - `!test` / `test` 指令可強制跳過檢查重新下載
- [x] 2026-01-02 修復 gallery-dl Windows 路徑過長問題
  - 修改 gallery-dl.conf 使用 `["nhentai", "{gallery_id}"]` 格式
  - 新增 `--config` 參數確保讀取設定檔
- [x] 2026-01-02 修復 PDF 輸出路徑過長問題
  - 資料夾名稱改用 `gallery_id` 而非完整標題
  - PDF 檔名改用 `{gallery_id}.pdf` 格式
  - 保留完整標題存入 metadata 和顯示
  - 新增 PDF save 詳細錯誤日誌
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
