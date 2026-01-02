# Implementation Plan

> 此檔案記錄開發進度與待辦事項。
> 每完成一個步驟，請將 `[ ]` 改為 `[x]`。

---

## ✅ Phase 0: Documentation (文件建立)
- [x] Step 0.1: 建立 Vibe Coding 文件架構
- [x] Step 0.2: 建立 Memory Bank 資料夾與模板
- [x] Step 0.3: 加強自動更新規則 (Auto-Update Protocol)
- [ ] Step 0.4: 進行顧問式訪談，收斂需求
- [ ] Step 0.5: 完善所有 Memory Bank 文件

---

## 📋 Phase 1: Foundation (基礎建設) - 已完成
> 此階段已由現有程式碼完成

- [x] Step 1.1: Discord Bot 基礎框架
- [x] Step 1.2: gallery-dl 整合
- [x] Step 1.3: PDF 轉換功能
- [x] Step 1.4: Eagle metadata 生成
- [x] Step 1.5: Docker 容器化

---

## 🚀 Phase 2: Enhancement (功能增強) - 進行中
> Eagle 插件開發

- [x] Step 2.1: Eagle NAS Auto-Importer 插件
  - 背景服務每 30 秒掃描 NAS 資料夾
  - 自動匯入 PDF 到 Eagle
  - 讀取 metadata.json 填寫標籤/網址/註釋
  - 匯入後歸檔到 imported 資料夾
- [ ] Step 2.2: [待確認功能]
- [ ] Step 2.3: [待確認功能]

---

## 🎮 Phase 3: UI Components (Discord 互動元件) - 進行中
> 使用 discord.py View/Button/Select 提升使用體驗

### Step 3.1: 基礎架構 ✅
- [x] 建立 `bot/views/` 資料夾結構
- [x] 實作持久化 View 基礎類別 (Bot 重啟後按鈕仍可用)
- [x] 設定 5 分鐘超時機制

### Step 3.2: SearchResultView (搜尋結果) ✅
- [x] Select Menu 選擇作品 → 自動執行 `/read`
- [x] 按鈕：`🔀 隨機一本`、`❌ 關閉`
- [x] custom_id 格式：`search_select`

### Step 3.3: ReadDetailView (詳情頁) ✅
- [x] 按鈕：`📄 開啟 PDF`、`🔗 nhentai`
- [x] 按鈕：`🔍 同作者`、`🔍 同原作`、`📥 重新下載`、`🔀 隨機一本`
- [x] **Tag Select Menu**：選擇標籤搜尋同類作品
- [x] custom_id 格式：`read_*`、`tag_select`、`artist_search:*`

### Step 3.4: RandomResultView (隨機結果) ✅
- [x] 按鈕：`📖 詳細資訊`、`📄 開啟 PDF`、`🔀 再抽一次`
- [x] 按鈕：`📥 下載此本`
- [x] custom_id 格式：`random_*`

### Step 3.5: DownloadCompleteView (下載完成) ✅
- [x] 按鈕：`📄 開啟 PDF`、`📖 查看詳情`、`🔗 nhentai`
- [x] 按鈕：`📥 繼續下載`
- [x] custom_id 格式：`dl_*`

### Step 3.6: PaginatedListView (分頁列表) - 可選
- [ ] 分頁按鈕：`⬅️ 上一頁`、`➡️ 下一頁`
- [ ] 快捷按鈕：`🔍 搜尋`、`🔀 隨機`

---

## 🔄 Phase 4: Refactoring (重構週期) - 待規劃
> 程式碼品質改善

- [ ] Step 4.1: 模組化拆分 (run.py 目前約 3800 行)
- [ ] Step 4.2: 新增單元測試
- [ ] Step 4.3: 錯誤處理優化

---

## 🧪 Phase 5: Testing (測試建立) - 待規劃

- [ ] Step 5.1: 建立測試框架
- [ ] Step 5.2: 核心功能單元測試
- [ ] Step 5.3: 整合測試

---

## 📝 Changelog (變更日誌)

### 2026-01-02 (v3.3.0) 🎮 UI Components
- **feat: Discord UI 互動元件整合**
  - 建立 `bot/views/` 模組化架構
  - `SearchResultView` - 搜尋結果 Select Menu → 一鍵查看詳情
  - `ReadDetailView` - 詳情頁按鈕 + Tag Select Menu
  - `RandomResultView` - 隨機結果操作按鈕
  - `DownloadCompleteView` - 下載完成後快捷按鈕
- **feat: Tag 搜尋功能**
  - 詳情頁 Tag Select Menu 可搜尋同類作品
  - 同作者/同原作 一鍵搜尋按鈕
- **feat: eagle_library.py 新增 `find_by_tag()` 方法**
- **fix: update_final_progress 使用 gallery_id 取代 media_id**

### 2026-01-02 (v3.1.0)
- **feat: `/random` downloads 使用 PDF URL**
  - downloads 來源改用 `http://192.168.0.32:8888/{id}/{id}.pdf`
  - 不再顯示 nhentai 網址
- **fix: `/random count` 顯示順序**
  - 一本顯示完再傳下一本
  - 先傳封面，再傳資訊
- **docs: 新增 Help-Sync 規則**
  - AI 修改指令時必須同步更新 /help
- **feat: `/random` 指令支援來源選擇**
  - 新增 `source` 參數：`eagle`、`downloads`、`all`
  - 預設從 Eagle Library 隨機
  - 可選擇從下載資料夾或全部來源隨機
  - 使用 `secrets` 模組提升隨機性
- **feat: `/list` 指令顯示全部本子**
  - 合併顯示 Eagle Library 和下載資料夾
  - 🦅 表示 Eagle，📁 表示下載資料夾
  - 顯示各來源統計數量
- **feat: 批次下載完成總結**
  - 多檔案下載完成後顯示統計
  - 顯示成功/失敗數量
  - 列出失敗的 Gallery ID
- **fix: 改善隨機演算法**
  - eagle_library.py 改用 `secrets.randbelow()` 
  - 提供加密安全等級的隨機選取

### 2026-01-02
- **feat: Eagle NAS Auto-Importer 插件**
  - 建立 `Eagle-Auto-Importer/` 插件目錄
  - `manifest.json` - 設定為 background service
  - `index.html` - 插件 UI 顯示服務狀態與日誌
  - `js/plugin.js` - 核心邏輯
    - 定時掃描 NAS 資料夾 (可設定間隔)
    - 自動匯入 PDF 檔案到 Eagle
    - 讀取 metadata.json 並更新 Eagle 項目資訊
    - 匯入成功後自動歸檔
  - 建立 `imported/` 資料夾用於歸檔
- **fix: PDF 等寬功能**
  - 改用 Pillow 取代 img2pdf 進行 PDF 轉換
  - 自動找出最大寬度，將所有圖片按比例縮放至統一寬度
  - 確保 PDF 每頁都是 100% 寬度對齊
  - 支援 RGBA/P/LA 等透明圖片模式轉換為 RGB
- 建立 Vibe Coding 文件架構
- 初始化 Memory Bank
