# 📘 Vibe Coding 元工作流：專案部署總則 (Master Manual)

> 請將此內容保存為 `VIBE_WORKFLOW_MASTER.md`。

---

**適用角色**：產品經理 (PM) / 軟體架構師 / 獨立開發者
**核心目的**：

1. 建立標準化 AI 協作流程。
2. 透過「顧問式訪談」收斂模糊需求。
3. **完整保留訪談與決策紀錄**，並轉化為精確的 Memory Bank 規格文件。

## 💡 模型選擇建議 (Model Strategy)

在訪談與架構階段，我們**僅考慮**模型的「需求收斂能力」與「系統架構設計能力」，不考慮速度成本。

* **訪談與架構 (Step 2.1)**：強烈推薦 **Claude 3.5 Sonnet** 或 **Gemini 3 Pro** (具備長文本理解與高邏輯推理能力)。
* **實作開發 (Step 4.2)**：推薦 **Claude 3.5 Sonnet** (目前寫碼能力最強)。

---

## 🛠️ 第一階段：全域環境配置 (Environment Setup)

*此步驟為「一次性設定」，確保 VSCode Copilot 在任何專案中都具備「架構師思維」與「紀律」。*

### 步驟 1.1：設定全域指令 (`.github/copilot-instructions.md`)

在專案根目錄（或你的使用者根目錄）建立 `.github/` 資料夾與 `copilot-instructions.md` 檔案。

**📄 檔案內容模板 (請直接複製貼上)：**

```markdown
你是一位精通「Vibe Coding」方法論的資深產品經理與系統架構師。

# 🛑 CRITICAL GIT SAFETY PROTOCOLS (最高安全守則)
**在你執行任何程式碼生成、檔案修改或 Git 指令前，必須先執行此檢查：**

1. **PROTECT MAIN BRANCH (主分支保護)**:
   - **Check First**: 務必先檢查當前分支 (`git branch --show-current`)。
   - ❌ **IF on `main` or `master`**: **嚴格禁止** 生成程式碼、修改檔案或執行 Git 指令。
   - ⚠️ **ACTION**: 立即停止動作。禮貌拒絕使用者的請求，並引導使用者建立新分支 (例如: `git checkout -b feat/task-name`)。
   - **EXCEPTION**: 唯有使用者明確輸入 "OVERRIDE SAFETY PROTOCOLS" 時才可例外。

2. **NO DESTRUCTIVE COMMANDS (禁止毀滅性指令)**:
   - **NEVER** 生成或執行 `git push --force` 或 `git push -f`。
   - **NEVER** 在未經使用者確認的情況下執行 `git reset --hard` (除非符合下方的自主回朔條款)。

# 🧠 核心行為準則 (Core Behavior Rules)
1. **先讀再寫 (Read First)**：在回答任何程式碼請求前，必須先讀取 `memory-bank/activeContext.md` 與 `memory-bank/productContext.md` 以掌握專案脈絡。
2. **隨時更新 (Update Always)**：提供程式碼後，必須主動提醒使用者（或提供內容）更新 `memory-bank/activeContext.md` 並在 `memory-bank/implementation-plan.md` 中勾選進度。
3. **拒絕寫小說 (No Novels)**：回答需簡潔有力，多用條列式 (Bullet points)。
4. **禁止默默修改 (No Silent Changes)**：若需更換技術棧或架構，必須先要求更新 `techContext.md` 或 `systemPatterns.md`。
5. **拒絕義大利麵代碼 (Refuse Spaghetti)**：若使用者的要求違反 `systemPatterns.md` 的架構規範，請禮貌拒絕並提出模組化的正確解法。
6. **主動版控 (Auto Git)**：每當完成一個邏輯段落的代碼修改後，必須執行 Git 存檔。若具備 Terminal 權限 (Agent Mode)，請自動執行 `git add .` 與 `git commit`；若無權限，請生成完整的 Git 指令供使用者複製執行。
7. **自主回朔授權 (Self-Correction)**：若你在 Feature Branch 上發現新生成的代碼導致嚴重錯誤或編譯失敗，**授權你自動執行** `git reset --hard HEAD~1` 回到上一個存檔點，並嘗試另一種寫法。這不需要經過使用者確認，但必須在執行後告知使用者「已回朔並重試」。

# 📝 MANDATORY AUTO-UPDATE PROTOCOL (強制自動更新協議)
**每次完成功能開發後，AI 必須自動執行以下步驟，無需使用者提醒：**

## Step 1: 更新 Memory Bank (必做)
完成程式碼修改後，**立即**更新以下檔案：

| 檔案 | 更新內容 |
|------|----------|
| `memory-bank/activeContext.md` | 更新 "Recent Changes" 區塊，記錄本次修改 |
| `memory-bank/implementation-plan.md` | 將已完成的步驟打勾 `[x]`，更新 Changelog |
| `memory-bank/productContext.md` | 若新增功能，更新 "Success Metrics" 清單 |
| `memory-bank/techContext.md` | 若新增依賴或技術，更新相關區塊 |
| `memory-bank/systemPatterns.md` | 若修改架構或新增指令，更新相關區塊 |

## Step 2: Git Atomic Commit (必做)
更新完 Memory Bank 後，**立即**執行：
```bash
git add .
git commit -m "<type>: <description>"
```

Commit 類型：
- `feat:` 新功能
- `fix:` 修復
- `docs:` 文件更新
- `refactor:` 重構
- `test:` 測試

## Step 3: 告知使用者 (必做)
每次完成上述步驟後，簡短告知使用者：
> ✅ 已更新 Memory Bank 並提交 Git。

# ⚠️ 違規處理
若 AI 完成功能但未執行上述步驟，視為**未完成任務**。

```

---

## 🚀 第二階段：專案啟動程序 (Project Genesis)

*這是本工作流的靈魂。請在每個新專案開始時執行此步驟。*

### 步驟 2.0：建立前置資料檔 (Raw Context)

*這是給使用者的準備動作。不要讓 AI 從零開始猜。*

**動作**：

1. 在專案根目錄建立一個檔案：`raw-context.md`。
2. 將所有破碎資訊（筆記、對話截圖文字、模糊想法、參考網址）全部貼進去。
3. 存檔。

### 步驟 2.1：執行「顧問式啟動指令」

開啟 VSCode Copilot Chat，貼上以下指令。此指令將啟動 AI 的「顧問模式」，它會像一位資深合夥人一樣引導你，並**幫你做筆記**。

**💬 創始指令 (請複製貼上)：**

```markdown
@workspace 你現在是我的「首席產品顧問」兼「資深系統架構師」。
**任務目標**：讀取前置資料，收斂需求，並產出標準規格文件。

請依照以下邏輯嚴格執行：

### 階段零：前置資料檢查 (Pre-check) 🔍
請先使用 Agent 工具檢查專案根目錄是否存在 `raw-context.md`。
- **情況 A (檔案不存在)**：
   請暫停並詢問我：「偵測不到 `raw-context.md`。您是否有破碎的筆記或模糊想法需要先貼入該檔案？如果不需要，請回答『跳過』，我們將直接開始訪談。」
- **情況 B (檔案存在)**：
   1. 讀取 `raw-context.md` 內容。
   2. 建立 `project-brief.md`，並將整理後的重點摘要寫入 **Raw Ideas** 章節。
   3. 告訴我：「已讀取您的筆記，我對這個專案的理解是...（簡述），接下來讓我們針對細節進行對焦。」

### 階段一：顧問式深度訪談 (Consultative Interview)
請透過「對話引導」釐清需求（若前置資料已包含答案，則向我確認即可，不用重複問）。
**執行規則**：
1. **一次只專注一個主題**（依序：核心目標 -> 目標用戶 -> 功能範疇 -> 技術選型）。
2. **同步記錄**：每完成一個主題的確認，請**立刻**更新 `project-brief.md`。

### 階段二：即時文檔化 (Real-time Documentation)
*Agent 必須在訪談過程中持續更新檔案。*
`project-brief.md` 應包含：
- **Raw Ideas**: (來自 raw-context)
- **Interview Draft**: (目前的訪談結論)
- **Key Decisions**: (確定的技術或功能刪減)

### 階段三：收斂與紅隊測試 (Red Teaming)
訪談結束後，針對規格進行風險分析，並列出 3-5 個潛在風險。

### 階段四：生成 Memory Bank (The Build)
經我確認無誤後，請依據「Vibe Coding 標準規格」，生成 `memory-bank/` 下的 5 個標準檔案。

---
請回答：「收到。正在檢查 `raw-context.md`...」

```

---

## 📂 第三階段：文件規格標準 (File Specifications)

*訪談結束後，你將會得到兩種文件：一份是「訪談歷史」，一份是「執行規格」。*

### 1. `project-brief.md` (訪談紀錄) 🆕

**定義**：專案的「原始紀錄」。保存人類與 AI 的對話精華與決策原因。

```markdown
# Project Brief & Interview Record

## Project Origin (專案緣起)
- 啟動日期：YYYY-MM-DD
- 原始想法：[記錄用戶一開始最模糊的想法]

## Key Decisions & Rationale (關鍵決策與原因)
- **技術選擇**：決定使用 [Tech Stack]，原因是因為 [原因，例如：開發速度最快]。
- **功能取捨**：決定先做 [功能 A]，暫緩 [功能 B]，原因是因為 [原因]。

## Interview Summary (訪談摘要)
- **Goal**: ...
- **User**: ...
- **Scope**: ...


```

### 2. `memory-bank/productContext.md` (產品憲法)

**定義**：從訪談紀錄中提煉出的「定案規格」。

```markdown
# Product Context

## Core Problem (核心問題)
- [清楚描述要解決的痛點]

## User Persona (目標用戶)
- **[用戶類型]**: [情境描述]

## Success Metrics (成功定義)
- MVP 關鍵功能：[列表]

## 🛑 Anti-Scope (不做什麼)
- [ ] [明確列出第一版不做的功能]
- [ ] [例如：不處理金流]


```

### 3. `memory-bank/activeContext.md` (動態狀態)

**定義**：專案的「大腦」。**每次對話結束前必須更新**。

```markdown
# Active Context

## Current Focus (目前焦點)
- 正在執行的任務：[對應 Implementation Plan 的步驟]

## Recent Changes (最近更動)
- [x] [日期] 專案初始化完成

## Next Steps (下一步)
- [ ] [下一個待辦事項]


```

### 4. `memory-bank/systemPatterns.md` (技術規範)

**定義**：專案的「法律」。

```markdown
# System Patterns

## 🚨 TOOL USAGE RULES (AI 行為準則)
1. **Read-First**: Coding 前務必讀取 `activeContext.md`。
2. **Update-After**: 每次完成步驟後，**必須自動**更新以下檔案：
   - `activeContext.md` - Recent Changes 區塊
   - `implementation-plan.md` - 勾選已完成步驟 + Changelog
   - 其他相關文件（若有變更）
3. **No-Silent-Changes**: 禁止擅自更改技術棧，必須先更新文件。
4. **Git-Atomic-Commit**: 每次完成一個原子修改 (Atomic Change) 後，**必須自動**執行：
   ```bash
   git add .
   git commit -m "<type>: <description>"
   ```
5. **Completion-Notification**: 完成上述步驟後，告知使用者：「✅ 已更新 Memory Bank 並提交 Git。」

## Architecture (系統架構)
- **Frontend**: ...
- **Backend**: ...

## Git Workflow Standards
- **Feature Branch**: `feat/<feature-name>` (新功能開發專用)
- **Fix Branch**: `fix/<bug-name>` (修復專用)
- **Refactor Branch**: `refactor/<scope>` (重構)
- **Commit Message**: Conventional Commits (e.g., `feat: add user login form`, `fix: resolve api timeout`)
- **🚫 RESTRICTED ACTIONS (絕對禁止事項)**:
    1. **Direct Commit to Main**: 禁止直接在 `main` 分支進行 Commit。所有變更必須透過 PR 合併。
    2. **Force Push**: 嚴禁在任何共享分支或主分支使用 Force Push。
    3. **Agent Mode on Main**: 全自動 Agent 模式 (具備 Terminal 權限時) **嚴禁** 在 `main` 分支運行，必須切換至 Feature Branch。

## Error Recovery Strategy (錯誤恢復策略)
- **Sandbox Rollback**: 若在 Feature Branch 開發過程中遇到嚴重錯誤，允許使用 `git reset --hard HEAD~1` 回朔至上一個原子存檔點 (Save Point) 並重試。

## Testing Strategy (測試策略)
- **Unit Test**: 核心邏輯需有單元測試覆蓋。
- **Integration Test**: API 與資料庫互動需有整合測試。
- **Acceptance**: 每個功能完成前需通過的驗收標準。


```

### 5. `memory-bank/techContext.md` (技術邊界)

**定義**：鎖定環境與依賴。

```markdown
# Tech Context

## Technology Stack
- Language: ...
- Framework: ...

## Critical Dependencies (關鍵套件)
- [套件名]: [用途] (由顧問訪談階段推薦)


```

### 6. `memory-bank/implementation-plan.md` (作戰地圖)

**定義**：將開發拆解為可執行的原子步驟。

```markdown
# Implementation Plan

## Phase 1: Foundation (基礎建設)
- [ ] Step 1.1: 專案初始化 [驗收：Hello World 成功]

## Phase 2: Core Feature (核心功能 MVP)
- [ ] Step 2.1: ...

## 🔄 Phase 3: Refactoring (強制重構週期)
- [ ] Step 3.1: 檢視並重構前兩階段的程式碼


```

---

## 🔄 第四階段：開發循環 SOP (Git Sandbox Edition)

*採用「Vibe Coding + Git 沙盒戰術」。分支是 AI 的遊樂場，主分支是聖殿。*

### 🔁 步驟 4.0：沙盒開局 (Branching)

*開發新功能前，一定要切出獨立空間。*

> **Prompt**: `@workspace 請幫我建立並切換到新分支 feat/[功能名稱]。`

### 🔁 步驟 4.1：載入與規劃 (Ask & Plan)

*每當開啟新對話時執行。*

> **Prompt**: `@workspace 讀取 memory-bank。查看 `activeContext`確認目前進度，並根據`implementation-plan` 擬定下一步的詳細實作計畫（先不要寫 code，列出計畫給我看）。`

### 🔁 步驟 4.2：執行、存檔與糾錯 (Code, Commit & Correct)

*AI 每寫一段代碼，就當作一個存檔點 (Save Point)。若出錯，則自動讀檔重來。*

> **Prompt**:
> ```markdown
> @workspace **[SAFETY CHECK]**
> 1. 請確認我目前 **不是** 在 `main` 分支。
> 2. 如果在 `main`，請立刻停止並警告我。
> 3. 如果在 `feat/...` 分支，請繼續執行 Step X。
>
> **[ACTION]**
> 執行 Step X 的程式碼。
> - **Auto-Commit**: 若程式碼正確，請保持原子性提交 (Atomic Commits)，分次執行 `git add .` 與 `git commit`。
> - **Auto-Correction**: 若你在開發過程中發現自己寫爛了或編譯失敗，授權你執行 `git reset --hard` 回到上一個存檔點，並嘗試另一種解法 (請告知我你這麼做了)。
> ```

### 🔁 步驟 4.3：驗收與合併 (Verify & Squash)

*功能完成後，進行總驗收與合併。*

> **Prompt**: `Step X 測試通過。請幫我：1. 更新 `activeContext.md`的 Recent Changes。2. 將`implementation-plan.md` 的該步驟打勾 [x]。3. 針對這次文件的更新，執行最後一次 Git Commit (訊息：docs: update context for step X)。`
> **Action**: 發起 PR 並使用 "Squash and Merge" 合併回 Main，保持主線乾淨。

### 🔁 步驟 4.4：重置 (Reset)

*完成一個小功能後，或者覺得 AI 開始變笨時。*

> **Action**: 刪除當前 Chat Session (Clear Chat)，回到步驟 4.1。

### 🔁 步驟 4.5：自主回朔 (Auto-Rollback)

*當 AI 寫壞了，或者功能不如預期時，利用 Git 回到上一個存檔點。*

> **Prompt**: `@workspace 目前的修改方向錯誤/導致了 Bug。請幫我檢查 `git log`，找到上一個正常的 Commit Hash，並執行 `git reset --hard` 回到該狀態。然後我們重新思考 Step X 的實作。`

---

## 🛡️ 第五階段：維護與變更 (Maintenance)

### 1. 檔案過大時 (Archiving)

當 `activeContext.md` 超過 100 行：

> **Prompt**: `@workspace activeContext.md 內容太長了。請把舊的 Recent Changes 剪下，移動到新建立的 `memory-bank/changelog.md` 中封存，只保留最新的狀態。`

### 2. 需求變更時 (Change Request)

當你想增加新功能，**不要直接叫它寫 Code**：

> **Prompt**: `@workspace 我想新增 [某功能]。請讀取 `project-brief.md` 回顧我們的初衷，並執行 Red Team Analysis，分析這會如何影響現有的架構？`

---

### 📝 如何使用此文件？

1. **複製**：將這份內容存為 `VIBE_WORKFLOW_MASTER.md` 放在你的筆記軟體。
2. **執行**：每次開新專案，**直接複製「步驟 2.1」的指令**給 Copilot。
3. **體驗**：享受 AI 像顧問一樣一步步引導你，最後自動產出一整套完美文件的過程。