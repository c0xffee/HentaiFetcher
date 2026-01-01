/**
 * nHentai Auto-Importer
 * 自動掃描 NAS 資料夾，匯入 PDF 並填寫 metadata
 * 
 * @version 1.0.0
 * @author HentaiFetcher
 */

const fs = require('fs');
const path = require('path');

// ==================== 設定區 ====================
const CONFIG = {
    // 監控來源 - NAS 下載資料夾 (使用 UNC 路徑)
    NAS_WATCH_PATH: '\\\\192.168.10.2\\docker\\HentaiFetcher\\downloads',
    
    // 歸檔目的地 - 匯入後移動到此資料夾
    IMPORTED_PATH: '\\\\192.168.10.2\\docker\\HentaiFetcher\\imported',
    
    // 掃描間隔 (毫秒) - 預設 30 秒
    SCAN_INTERVAL: 30000,
    
    // 支援的檔案類型
    SUPPORTED_EXTENSIONS: ['.pdf'],
    
    // 是否在啟動時立即掃描
    SCAN_ON_START: true,
    
    // 是否啟用詳細日誌
    DEBUG: true
};

// ==================== 狀態變數 ====================
let isScanning = false;
let importedCount = 0;
let scanTimer = null;
let logs = [];

// ==================== 工具函數 ====================

/**
 * 記錄日誌
 */
function log(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString('zh-TW');
    const logEntry = { time: timestamp, message, type };
    logs.unshift(logEntry);
    
    // 保留最近 50 條日誌
    if (logs.length > 50) {
        logs = logs.slice(0, 50);
    }
    
    // 控制台輸出
    const prefix = {
        'info': '[INFO]',
        'success': '[SUCCESS]',
        'error': '[ERROR]',
        'warn': '[WARN]'
    }[type] || '[LOG]';
    
    console.log(`${prefix} ${timestamp} - ${message}`);
    
    // 更新 UI
    updateLogUI();
}

/**
 * 更新 UI 日誌區域
 */
function updateLogUI() {
    const logArea = document.getElementById('logArea');
    if (!logArea) return;
    
    logArea.innerHTML = logs.slice(0, 10).map(entry => `
        <div class="log-entry ${entry.type}">
            <span class="log-time">[${entry.time}]</span> ${entry.message}
        </div>
    `).join('');
}

/**
 * 更新 UI 統計數據
 */
function updateStatsUI(pending = null) {
    const importCountEl = document.getElementById('importCount');
    const pendingCountEl = document.getElementById('pendingCount');
    const watchPathEl = document.getElementById('watchPath');
    const archivePathEl = document.getElementById('archivePath');
    const scanIntervalEl = document.getElementById('scanInterval');
    
    if (importCountEl) importCountEl.textContent = importedCount;
    if (pendingCountEl && pending !== null) pendingCountEl.textContent = pending;
    if (watchPathEl) watchPathEl.textContent = CONFIG.NAS_WATCH_PATH.split('\\').pop();
    if (archivePathEl) archivePathEl.textContent = CONFIG.IMPORTED_PATH.split('\\').pop();
    if (scanIntervalEl) scanIntervalEl.textContent = `${CONFIG.SCAN_INTERVAL / 1000}s`;
}

/**
 * 確保目錄存在
 */
function ensureDir(dirPath) {
    try {
        if (!fs.existsSync(dirPath)) {
            fs.mkdirSync(dirPath, { recursive: true });
            log(`建立目錄: ${dirPath}`, 'info');
        }
        return true;
    } catch (err) {
        log(`建立目錄失敗: ${dirPath} - ${err.message}`, 'error');
        return false;
    }
}

/**
 * 讀取 JSON 檔案
 */
function readJsonFile(filePath) {
    try {
        const content = fs.readFileSync(filePath, 'utf-8');
        return JSON.parse(content);
    } catch (err) {
        log(`讀取 JSON 失敗: ${filePath} - ${err.message}`, 'error');
        return null;
    }
}

/**
 * 移動資料夾 (含所有內容)
 */
function moveFolder(source, destination) {
    try {
        // 確保目標目錄存在
        ensureDir(path.dirname(destination));
        
        // 如果目標已存在，先刪除
        if (fs.existsSync(destination)) {
            fs.rmSync(destination, { recursive: true, force: true });
            log(`覆蓋已存在的目標資料夾`, 'warn');
        }
        
        // 使用 rename 移動 (同一磁碟機更快)
        try {
            fs.renameSync(source, destination);
        } catch (renameErr) {
            // 如果 rename 失敗 (跨磁碟機)，使用複製後刪除
            copyFolderRecursive(source, destination);
            fs.rmSync(source, { recursive: true, force: true });
        }
        
        return true;
    } catch (err) {
        log(`移動資料夾失敗: ${err.message}`, 'error');
        return false;
    }
}

/**
 * 遞迴複製資料夾
 */
function copyFolderRecursive(source, destination) {
    ensureDir(destination);
    
    const items = fs.readdirSync(source);
    for (const item of items) {
        const srcPath = path.join(source, item);
        const destPath = path.join(destination, item);
        const stat = fs.statSync(srcPath);
        
        if (stat.isDirectory()) {
            copyFolderRecursive(srcPath, destPath);
        } else {
            fs.copyFileSync(srcPath, destPath);
        }
    }
}

/**
 * 取得資料夾內的 PDF 檔案
 */
function getPdfFiles(folderPath) {
    try {
        const files = fs.readdirSync(folderPath);
        return files.filter(file => {
            const ext = path.extname(file).toLowerCase();
            return CONFIG.SUPPORTED_EXTENSIONS.includes(ext);
        });
    } catch (err) {
        log(`讀取資料夾失敗: ${folderPath} - ${err.message}`, 'error');
        return [];
    }
}

// ==================== 核心邏輯 ====================

/**
 * 處理單一漫畫資料夾
 */
async function processComicFolder(folderPath, folderName) {
    log(`處理中: ${folderName}`, 'info');
    
    // 1. 檢查是否有 PDF 檔案
    const pdfFiles = getPdfFiles(folderPath);
    if (pdfFiles.length === 0) {
        log(`跳過 (無 PDF): ${folderName}`, 'warn');
        return false;
    }
    
    // 2. 讀取 metadata.json (如果存在)
    const metadataPath = path.join(folderPath, 'metadata.json');
    let metadata = null;
    if (fs.existsSync(metadataPath)) {
        metadata = readJsonFile(metadataPath);
        if (metadata) {
            log(`已讀取 metadata: ${metadata.name || folderName}`, 'info');
        }
    } else {
        log(`無 metadata.json: ${folderName}`, 'warn');
    }
    
    // 3. 匯入每個 PDF 檔案
    for (const pdfFile of pdfFiles) {
        const pdfPath = path.join(folderPath, pdfFile);
        
        try {
            // 準備匯入選項
            const importOptions = {};
            if (metadata) {
                if (metadata.name) importOptions.name = metadata.name;
                if (metadata.url) importOptions.website = metadata.url;
                if (metadata.tags && Array.isArray(metadata.tags)) importOptions.tags = metadata.tags;
                if (metadata.annotation) importOptions.annotation = metadata.annotation;
            }
            
            // 使用 Eagle API 匯入檔案 (帶 metadata)
            log(`匯入 PDF: ${pdfFile}`, 'info');
            
            const itemId = await eagle.item.addFromPath(pdfPath, importOptions);
            
            if (itemId) {
                log(`匯入成功, ID: ${itemId}`, 'success');
                
                // 設定自定義封面 (如果有 cover.jpg)
                const coverPath = path.join(folderPath, 'cover.jpg');
                if (fs.existsSync(coverPath)) {
                    try {
                        const item = await eagle.item.getById(itemId);
                        if (item) {
                            await item.setCustomThumbnail(coverPath);
                            log(`已設定封面: ${metadata?.name || folderName}`, 'success');
                        }
                    } catch (coverErr) {
                        log(`設定封面失敗: ${coverErr.message}`, 'warn');
                    }
                }
                
                importedCount++;
                updateStatsUI();
            } else {
                log(`匯入失敗: ${pdfFile}`, 'error');
            }
        } catch (err) {
            log(`匯入錯誤: ${pdfFile} - ${err.message}`, 'error');
        }
    }
    
    // 5. 歸檔 - 移動整個資料夾
    const destPath = path.join(CONFIG.IMPORTED_PATH, folderName);
    if (moveFolder(folderPath, destPath)) {
        log(`已歸檔: ${folderName}`, 'success');
        return true;
    } else {
        log(`歸檔失敗: ${folderName}`, 'error');
        return false;
    }
}

/**
 * 掃描 NAS 資料夾
 */
async function scanNasFolder() {
    if (isScanning) {
        log('掃描中，跳過本次...', 'warn');
        return;
    }
    
    isScanning = true;
    log('開始掃描 NAS 資料夾...', 'info');
    
    try {
        // 確保監控路徑存在
        if (!fs.existsSync(CONFIG.NAS_WATCH_PATH)) {
            log(`監控路徑不存在: ${CONFIG.NAS_WATCH_PATH}`, 'error');
            isScanning = false;
            return;
        }
        
        // 確保歸檔路徑存在
        ensureDir(CONFIG.IMPORTED_PATH);
        
        // 讀取所有子資料夾
        const items = fs.readdirSync(CONFIG.NAS_WATCH_PATH);
        const folders = items.filter(item => {
            // 忽略隱藏檔案
            if (item.startsWith('.')) return false;
            
            const itemPath = path.join(CONFIG.NAS_WATCH_PATH, item);
            try {
                return fs.statSync(itemPath).isDirectory();
            } catch {
                return false;
            }
        });
        
        log(`發現 ${folders.length} 個資料夾`, 'info');
        updateStatsUI(folders.length);
        
        // 處理每個資料夾
        let processedCount = 0;
        for (const folder of folders) {
            const folderPath = path.join(CONFIG.NAS_WATCH_PATH, folder);
            const success = await processComicFolder(folderPath, folder);
            if (success) {
                processedCount++;
            }
        }
        
        if (processedCount > 0) {
            log(`本次掃描完成，處理 ${processedCount} 個項目`, 'success');
        } else {
            log('掃描完成，無新項目', 'info');
        }
        
        updateStatsUI(folders.length - processedCount);
        
    } catch (err) {
        log(`掃描錯誤: ${err.message}`, 'error');
    }
    
    isScanning = false;
}

// ==================== 插件生命週期 ====================

/**
 * 插件建立時
 */
eagle.onPluginCreate((plugin) => {
    console.log('nHentai Auto-Importer 已載入');
    console.log('Plugin Info:', plugin);
});

/**
 * 插件執行時
 */
eagle.onPluginRun(async () => {
    log('📚 nHentai Auto-Importer 啓動', 'success');
    log(`監控路徑: ${CONFIG.NAS_WATCH_PATH}`, 'info');
    log(`歸檔路徑: ${CONFIG.IMPORTED_PATH}`, 'info');
    log(`掃描間隔: ${CONFIG.SCAN_INTERVAL / 1000} 秒`, 'info');
    
    updateStatsUI();
    
    // 立即執行一次掃描
    if (CONFIG.SCAN_ON_START) {
        setTimeout(() => {
            scanNasFolder();
        }, 2000); // 延遲 2 秒，讓 UI 先載入
    }
    
    // 設定定時掃描
    scanTimer = setInterval(() => {
        scanNasFolder();
    }, CONFIG.SCAN_INTERVAL);
    
    log(`已啟動定時掃描 (每 ${CONFIG.SCAN_INTERVAL / 1000} 秒)`, 'info');
});

/**
 * 插件顯示時
 */
eagle.onPluginShow(() => {
    log('插件視窗已顯示', 'info');
    updateStatsUI();
    updateLogUI();
});

/**
 * 插件隱藏時
 */
eagle.onPluginHide(() => {
    console.log('插件視窗已隱藏');
});

/**
 * 插件關閉前 (清理資源)
 */
eagle.onPluginBeforeExit(() => {
    log('插件正在關閉...', 'warn');
    if (scanTimer) {
        clearInterval(scanTimer);
        scanTimer = null;
    }
});

// ==================== 匯出設定 (供外部使用) ====================
if (typeof module !== 'undefined') {
    module.exports = { CONFIG, scanNasFolder };
}
