# Active Context

## Current Focus (目前焦點)
- 正在執行的任務：Eagle Library 整合 Discord Bot 搜尋功能

## Recent Changes (最近更動)
- [x] 2026-01-02 新增 !reindex 指令
  - 新增 `@bot.command(name='reindex')` 指令重建索引
  - 支援 aliases: rebuild, sync
  - 更新 known_commands 讓專用頻道可識別
  - 更新 !help 說明加入 !reindex
- [x] 2026-01-02 實作 rebuild_index() 功能
  - 掃描 Eagle Library images 目錄
  - 讀取每個項目的 metadata.json
  - 重建 imports-index.json 索引 (12 → 22 項)
- [x] 2026-01-02 修復專用頻道指令識別
  - 加入 known_commands 列表
  - 優先檢查是否為指令再處理下載
- [x] 2026-01-02 建立 eagle_library.py 模組
  - EagleLibrary 類別查詢 Eagle Library
  - 支援 find_by_nhentai_id, find_by_title, find_by_eagle_id
  - 生成 Web Station URL (http://192.168.10.2:8889/)
- [x] 2026-01-02 新增 !search, !read, !eagle 指令
  - !search <關鍵字> 搜尋 Eagle Library
  - !read <ID> 取得 PDF 閱讀連結
  - !eagle 顯示統計資訊
- [x] 2026-01-02 修復 Eagle API 路徑錯誤 (File URL path must be absolute)
  - 新增 `validateAbsolutePath()` 函數驗證路徑格式
  - 新增 `normalizePathForEagle()` 函數正規化路徑
- [x] 2026-01-02 建立 Eagle NAS Auto-Importer 插件

## Next Steps (下一步)
- [ ] 測試 !reindex 指令
- [ ] 測試搜尋與閱讀功能
- [ ] 完整測試 Eagle Auto-Importer 流程

## Open Questions (待解決問題)
- [ ] 是否需要定期自動重建索引？
- [ ] 是否需要搜尋結果分頁功能？
- [ ] 測試策略如何規劃？

## Notes (備註)
- 專案版本：v2.8.0
- 主要程式：run.py (約 2800 行)
