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
# 🤖 Vibe Coding Agent Protocols (Zero-Decay Edition)

你是一位資深架構師與開發者。你的核心職責不僅是寫出能動的 Code，更是維護「專案記憶 (Memory Bank)」的絕對準確性。

# 💎 THE GOLDEN RULE (黃金法則)
**"Documentation is not a chore; it is the source of truth."**
任何程式碼的變更若未同步反映在 `memory-bank/` 中，該次變更即視為 **失敗 (Failure)**。
我們寧可要「準確的文件 + 尚能改進的代碼」，也不要「完美的代碼 + 過時的文件」。

# 🛑 SAFETY & IDENTITY CHECKS (安全與身分驗證)
**每回合動作前必須執行：**
1. **Identity Check**: 執行 `git branch --show-current`。
   - 若為 `main` 或 `master`：⛔ **拒絕執行**，除非收到 "OVERRIDE" 指令。
   - 若為 `feat/...` 或 `fix/...`：✅ **允許執行**。
2. **Context Check**: 讀取 `activeContext.md` 確保你清楚當前的任務目標。

# ⚙️ ZERO-DECAY WORKFLOW (零衰退工作流)

**在執行任何 Coding 任務時，必須嚴格遵守以下「三步走」節奏：**

## Step 1: Pre-Implementation Analysis (實作前分析)
*在寫任何 Python/JS 代碼之前，先告訴我你要改什麼文件。*
思考並列出：
- 這會影響 `systemPatterns.md` 的架構嗎？(如：新資料夾、新資料流)
- 這會增加 `techContext.md` 的依賴嗎？(如：pip install, 新的 import)
- 這完成了 `implementation-plan.md` 的哪一步？
- 這是否改變了產品的使用者體驗 (Product Context)？

## Step 2: Implementation (實作)
執行程式碼修改。

## Step 3: Synchronized Commit (同步提交)
**🔴 嚴格禁止單獨提交程式碼檔案。**
你生成的 Git 指令**必須**同時包含程式碼與文件的變更。

**正確範例 (Correct):**
# 修改了功能，同時更新了 activeContext 和 implementation-plan
git add run.py memory-bank/activeContext.md memory-bank/implementation-plan.md
git commit -m "feat: implement pdf scaling and update context"



**錯誤範例 (Wrong - 禁止使用):**

git add run.py
git commit -m "feat: implement pdf scaling" 
# ❌ 違規：沒有包含 memory-bank 的更新

Commit 類型：

* `feat:` 新功能
* `fix:` 修復
* `docs:` 文件更新
* `refactor:` 重構
* `test:` 測試

# 🧠 MEMORY BANK MAINTENANCE RULES (記憶庫維護規則)

1. **activeContext.md (實時狀態)**
* **觸發時機**: *每次*對話結束前。
* **動作**: 更新 "Recent Changes"，將剛做完的事項從 "Next Steps" 移到 "Recent Changes"。


2. **implementation-plan.md (進度追蹤)**
* **觸發時機**: 完成一個子任務 (Step x.x) 時。
* **動作**: 將 `[ ]` 改為 `[x]`。若發現原本計畫不足，請*立即*插入新步驟。


3. **systemPatterns.md (架構圖)**
* **觸發時機**: 新增檔案、修改資料夾結構、改變核心邏輯時。
* **動作**: **必須**更新 ASCII 架構圖或 File Structure 區塊。
* **原則**: 不要等到最後才改，現在就改。


4. **techContext.md (技術棧)**
* **觸發時機**: 修改 `requirements.txt`, `package.json`, `Dockerfile` 時。
* **動作**: 同步更新依賴列表。


5. **productContext.md (產品憲法)**
* **觸發時機**:
* 新增功能 (New Feature)
* 修改既有功能需求 (Requirement Change)
* 明確定義「不做什麼」 (Anti-Scope Refinement)


* **動作**: 更新 "User Stories"、"Success Metrics" 或 "Anti-Scope"。確保任何功能變更都有對應的使用者故事支持。



# 🚀 PROACTIVE BEHAVIOR (主動行為)

* **不要等我提醒**：如果你發現 `productContext.md` 裡的 "Anti-Scope" 定義模糊，請主動詢問我。
* **拒絕模糊指令**：如果我叫你「隨便做個功能」，請引用 `productContext.md` 的設計原則來反問我細節。

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

**定義**：專案的最高指導原則。這不是功能清單，而是「為什麼要做」以及「如何思考」的準則。

```markdown
# Product Context

## Core Problem (核心問題)
- [一句話描述痛點]：例如「使用者無法在手機上管理 NAS 的漫畫收藏」。
- [一句話描述解法]：例如「透過 Discord Bot 作為遙控器，自動化下載與歸檔」。

## User Stories (使用者故事)
*描述用戶在什麼情境下，想要做什麼，以達到什麼目的。*
- 作為 **[收藏家]**，我想要 **[貼上網址就自動下載]**，以便 **[省去手動操作 NAS 的時間]**。
- 作為 **[Eagle 用戶]**，我想要 **[檔案自動擁有標籤]**，以便 **[未來能快速搜尋]**。

## Success Metrics (成功定義)
- **系統面**：轉換 PDF 失敗率低於 1%。
- **體驗面**：指令回應時間 < 2秒。

## Design Principles (設計原則)
- **Zero Config**: 用戶不需要進入 NAS 後台設定。
- **Auto-Healing**: 下載失敗必須自動重試或通知，不能默默失敗。

## 🛑 Anti-Scope (邊界與限制)
*明確定義「不做」什麼，防止範圍蔓延 (Scope Creep)。*
- [ ] 第一版不支援付費網站 (Fantia/Fanbox)。
- [ ] 不實作 Web UI，全靠 Discord 互動。

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
   git add .
   git commit -m "<type>: <description>"
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

> **Prompt**: 
> ```markdown
> @workspace 讀取 memory-bank。查看 `activeContext`確認目前進度，並根據`implementation-plan` 擬定下一步的詳細實作計畫（先不要寫 code，列出計畫給我看）。
> ```

### 🔁 步驟 4.2：同步開發循環 (Sync-Locked Development)

*此指令強制 AI 將代碼與文件視為一體，確保零衰退。*

> **Prompt**:
> ```markdown
> @workspace **[ZERO-DECAY MODE]**
>
> 1. **Check Identity**: 確認目前分支不是 `main`。
>
> 2. **Analysis**: 讀取 `activeContext.md` 與 `implementation-plan.md`，確認我們現在要解哪一個步驟？
>
> 3. **Execution Plan**:
>    請執行任務：[描述任務內容]
>
>    **⚠️ 關鍵要求**:
>    - 你的輸出必須包含**程式碼變更** 以及 **對應的 Memory Bank 文件更新**。
>    - 尤其是 `activeContext.md` (狀態) 與 `implementation-plan.md` (進度)。
>    - 如果涉及架構變動，請一併更新 `systemPatterns.md`。
>
> 4. **Atomic Commit**:
>    最後生成的 git commit 指令，**必須同時 `git add` 程式碼檔案與 Memory Bank 檔案**。
>
> 5. **Auto-Commit**: 若程式碼正確，請保持原子性提交 (Atomic Commits)，分次執行 `git add .` 與 `git commit`。
> 6. **Auto-Correction**: 若你在開發過程中發現自己寫爛了或編譯失敗，授權你執行 `git reset --hard` 回到上一個存檔點，並嘗試另一種解法 (請告知我你這麼做了)。
> ```

### 🔁 步驟 4.3：驗收與合併 (Verify & Squash)

*功能完成後，進行總驗收與合併。*

> **Prompt**: 
> ```markdown
> Step X 測試通過。請幫我：1. 更新 `activeContext.md`的 Recent Changes。2. 將`implementation-plan.md` 的該步驟打勾 [x]。3. 針對這次文件的更新，執行最後一次 Git Commit (訊息：docs: update context for step X)。
> ```
> **Action**: 發起 PR 並使用 "Squash and Merge" 合併回 Main，保持主線乾淨。

### 🔁 步驟 4.4：重置 (Reset)

*完成一個小功能後，或者覺得 AI 開始變笨時。*

> **Action**: 刪除當前 Chat Session (Clear Chat)，回到步驟 4.1。

### 🔁 步驟 4.5：自主回朔 (Auto-Rollback)

*當 AI 寫壞了，或者功能不如預期時，利用 Git 回到上一個存檔點。*

> **Prompt**: `@workspace 目前的修改方向錯誤/導致了 Bug。請幫我檢查 `git log`，找到上一個正常的 Commit Hash，並執行 `git reset --hard` 回到該狀態。然後我們重新思考 Step X 的實作。`


### 🔁 步驟 4.6：Memory Bank 總體檢 (Health Check)

*當你發現 `activeContext` 與程式碼脫節，或 `productContext` 不再準確時，執行此指令。*

> **Prompt**:
> ```markdown
> @workspace 執行「Memory Bank 總體檢」。
> 1. **Codebase Audit**: 掃描 `systemPatterns.md` 與 `techContext.md`，檢查是否與目前的程式碼結構（如 `filelist.txt`）或 `package.json` 有出入？(例如：有沒有新的資料夾？有沒有棄用的套件？)
> 2. **Status Check**: 檢查 `implementation-plan.md` 的打勾項目，是否真的都完成了？
> 3. **Consistency Check**: 檢查 `productContext.md` 的目標是否仍符合我們目前的開發方向？
> 4. 請列出差異報告，並幫我更新 Memory Bank 使其恢復「單一真實來源 (Single Source of Truth)」的狀態。
> 
> ```
> 
> 

---

## 🛡️ 第五階段：變更管理與擴充 (Change Management)

*適用情境：專案開發到一半，突然有新點子，或想修改既有邏輯。*

### 5.1 微型變更 (Micro Changes)

*不影響架構的小修改（如：UI 調整、參數修改、Bug Fix）。*

* **Action**: 直接在 `fix/...` 分支執行，完成後觸發 Auto-Update Protocol 更新 `activeContext.md` 即可。

### 5.2 結構性擴充 (Structural Expansion) - **關鍵流程**

*影響架構的新功能（如：新增 Eagle 插件、更換 PDF 引擎）。*

**這是最容易導致 Memory Bank 脫節的時刻。請嚴格執行以下流程：**

1. **Step 1: 影響力分析 (Impact Analysis)**
> **Prompt**: 
> ```markdown
> @workspace 我想新增功能：[描述功能]。請讀取 `productContext.md`確認是否符合設計原則？並執行 Red Team Analysis分析此功能對`systemPatterns`(架構) 和`techContext` (依賴) 的衝擊。我們需要修改哪些檔案？
> ```


2. **Step 2: 規格更新 (Spec Update)**
*在寫任何 Code 之前，先叫 AI 改文件。*
> **Prompt**:
> ```markdown
>@workspace 確認執行。請幫我：
> 1. 更新 `productContext.md` (若有新 User Story)。
> 2. 在 `implementation-plan.md` 插入新的 Phase 或 Step。
> 3. 更新 `activeContext.md` 將焦點轉移到這個新任務。`
> ```
> 


3. **Step 3: 執行開發 (Execute)**
> 轉回標準開發流程 (Step 4.0)，切出新分支 `feat/new-feature` 開始實作。



---

### 📝 如何使用此文件？

1. **複製**：將這份內容存為 `VIBE_WORKFLOW_MASTER.md` 放在你的筆記軟體。
2. **執行**：每次開新專案，**直接複製「步驟 2.1」的指令**給 Copilot。
3. **體驗**：享受 AI 像顧問一樣一步步引導你，最後自動產出一整套完美文件的過程。