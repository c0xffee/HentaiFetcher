# Active Context

## Current Focus (目前焦點)
- 斜線指令版本 v3.1.0 - 功能增強

## Recent Changes (最近更動)
- [x] 2026-01-02 `/random` downloads 來源使用 PDF 連結
  - 改為 http://192.168.0.32:8888/{id}/{id}.pdf
  - 不再顯示 nhentai 網址
- [x] 2026-01-02 `/random count` 顯示順序修正
  - 一本顯示完再傳下一本
  - 先傳封面，再傳資訊
- [x] 2026-01-02 `/help` 新增 `/sync` 指令說明
- [x] 2026-01-02 systemPatterns.md 新增 Help-Sync 規則
- [x] 2026-01-02 `/random` 預設改為雙來源 (all)
  - 預設從 Eagle + Downloads 合併隨機
  - 新增 `/sync` 指令強制同步斜線指令
- [x] 2026-01-02 `/list` 顯示詳細統計
  - 分別顯示 Eagle/Downloads 數量
- [x] 2026-01-02 `/random` 指令支援來源選擇
  - 新增 `source` 參數：eagle、downloads、all
  - 使用 `secrets` 模組提升隨機性
- [x] 2026-01-02 `/list` 指令顯示全部本子
  - 合併 Eagle Library 和下載資料夾
  - 🦅/📁 來源標示
- [x] 2026-01-02 批次下載完成總結
  - 多檔下載完成後顯示統計 (成功/失敗)
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
- [ ] 重新部署 Docker 並測試新功能
- [ ] 測試 `/random` 來源參數
- [ ] 測試批次下載總結功能

## Notes (備註)
- 專案版本：v3.1.0
- 主要程式：run.py
