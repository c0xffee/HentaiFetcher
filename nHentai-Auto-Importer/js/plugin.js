/**
 * nHentai Auto-Importer
 * 自動掃描 NAS 資料夾，匯入 PDF 並填寫 metadata
 * 
 * @version 1.0.1
 * @author HentaiFetcher
 * 
 * 注意：Eagle API addFromPath 需要普通的檔案路徑字串，不需要 file:// URL
 */

const fs = require('fs');
const path = require('path');

// ==================== 設定區 ====================
const CONFIG = {
    // 監控來源 - NAS 下載資料夾
    // ⚠️ 重要：必須使用映射磁碟機路徑 (如 Z:\)，UNC 路徑 (\\IP\...) 會導致 Eagle API 錯誤
    // 設定方式: 在 Windows 執行 net use Z: \\192.168.10.2\docker
    NAS_WATCH_PATH: 'Z:\\HentaiFetcher\\downloads',
    
    // 歸檔目的地 - 匯入後移動到此資料夾
    IMPORTED_PATH: 'Z:\\HentaiFetcher\\imported',
    
    // 掃描間隔 (毫秒) - 預設 30 秒
    SCAN_INTERVAL: 30000,
    
    // 支援的檔案類型
    SUPPORTED_EXTENSIONS: ['.pdf'],
    
    // 是否在啟動時立即掃描
    SCAN_ON_START: true,
    
    // 是否啟用詳細日誌
    DEBUG: true,
    
    // ==================== Web URL 索引設定 ====================
    // Synology Web Station 端點:
    // - 8888: downloads 資料夾 (匯入前)
    // - 8889: Eagle Library images 資料夾 (匯入後)
    WEB_BASE_URL_DOWNLOADS: 'http://192.168.10.2:8888',
    WEB_BASE_URL_EAGLE: 'http://192.168.10.2:8889',
    
    // 匯入索引檔案路徑 (供 Discord Bot 讀取)
    INDEX_FILE_PATH: 'Z:\\HentaiFetcher\\imports-index.json'
};

/**
 * 驗證路徑是否為有效的絕對路徑 (非 UNC)
 * Eagle API 不支援 UNC 路徑 (\\IP\share)，必須使用映射磁碟機 (Z:\)
 */
function validateAbsolutePath(filePath) {
    // 檢查是否為 UNC 路徑
    if (filePath.startsWith('\\\\')) {
        return {
            valid: false,
            error: 'UNC 路徑不被 Eagle API 支援，請使用映射磁碟機 (如 Z:\\)'
        };
    }
    
    // 檢查是否為標準 Windows 絕對路徑 (C:\, D:\, Z:\ 等)
    const driveLetterPattern = /^[A-Za-z]:\\/;
    if (!driveLetterPattern.test(filePath)) {
        return {
            valid: false,
            error: `無效的絕對路徑格式: ${filePath}`
        };
    }
    
    return { valid: true };
}

/**
 * 將路徑正規化為 Eagle API 可接受的格式
 */
function normalizePathForEagle(filePath) {
    // 使用 path.normalize 處理路徑
    let normalized = path.normalize(filePath);
    
    // 確保使用反斜線 (Windows 標準)
    normalized = normalized.replace(/\//g, '\\');
    
    // 移除結尾的反斜線 (如果有)
    if (normalized.endsWith('\\') && !normalized.match(/^[A-Za-z]:\\$/)) {
        normalized = normalized.slice(0, -1);
    }
    
    return normalized;
}

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
 * 寫入 JSON 檔案
 */
function writeJsonFile(filePath, data) {
    try {
        const content = JSON.stringify(data, null, 2);
        fs.writeFileSync(filePath, content, 'utf-8');
        return true;
    } catch (err) {
        log(`寫入 JSON 失敗: ${filePath} - ${err.message}`, 'error');
        return false;
    }
}

/**
 * 讀取匯入索引
 */
function loadImportsIndex() {
    if (fs.existsSync(CONFIG.INDEX_FILE_PATH)) {
        const data = readJsonFile(CONFIG.INDEX_FILE_PATH);
        if (data && data.imports) {
            return data;
        }
    }
    // 初始化新索引
    return {
        webBaseUrlDownloads: CONFIG.WEB_BASE_URL_DOWNLOADS,
        webBaseUrlEagle: CONFIG.WEB_BASE_URL_EAGLE,
        lastUpdated: new Date().toISOString(),
        imports: {}
    };
}

/**
 * 儲存匯入索引
 */
function saveImportsIndex(indexData) {
    indexData.lastUpdated = new Date().toISOString();
    return writeJsonFile(CONFIG.INDEX_FILE_PATH, indexData);
}

/**
 * 從 URL 或 annotation 中提取 nhentai ID
 */
function extractNhentaiId(metadata) {
    // 優先從 URL 提取: https://nhentai.net/g/123456/
    if (metadata.url) {
        const urlMatch = metadata.url.match(/nhentai\.net\/g\/(\d+)/);
        if (urlMatch) return urlMatch[1];
    }
    
    // 從 annotation 中提取: 📔 ID: 123456
    if (metadata.annotation) {
        const annotationMatch = metadata.annotation.match(/📔 ID: (\d+)/);
        if (annotationMatch) return annotationMatch[1];
    }
    
    return null;
}

/**
 * 新增項目到索引
 * @param {string} folderName - 資料夾名稱 (作為 key)
 * @param {string} eagleItemId - Eagle item ID
 * @param {string} eagleFilePath - Eagle 中的完整檔案路徑
 * @param {object} metadata - 原始 metadata
 */
function addToImportsIndex(folderName, eagleItemId, eagleFilePath, metadata = {}) {
    try {
        const indexData = loadImportsIndex();
        const libraryPath = eagle.library.path;
        const imagesPath = path.join(libraryPath, 'images');
        
        // 計算相對於 images 資料夾的路徑
        let relativePath = eagleFilePath;
        if (eagleFilePath.startsWith(imagesPath)) {
            relativePath = eagleFilePath.substring(imagesPath.length);
        }
        // 轉換為 URL 格式 (使用正斜線)
        relativePath = relativePath.replace(/\\/g, '/');
        if (relativePath.startsWith('/')) {
            relativePath = relativePath.substring(1);
        }
        
        // URL 編碼 (處理中日文檔名)
        const encodedPath = relativePath.split('/').map(segment => encodeURIComponent(segment)).join('/');
        // 使用 8889 端口 (Eagle Library images 資料夾)
        const webUrl = `${CONFIG.WEB_BASE_URL_EAGLE}/${encodedPath}`;
        
        // 提取 nhentai ID
        const nhentaiId = extractNhentaiId(metadata);
        
        // 儲存到索引
        indexData.imports[folderName] = {
            eagleItemId: eagleItemId,
            eaglePath: relativePath,
            webUrl: webUrl,
            nhentaiId: nhentaiId,
            nhentaiUrl: metadata.url || null,
            title: metadata.name || folderName,
            tags: metadata.tags || [],
            importedAt: new Date().toISOString()
        };
        
        if (saveImportsIndex(indexData)) {
            log(`已更新索引: ${folderName}`, 'success');
            log(`Web URL: ${webUrl}`, 'info');
            return true;
        }
        return false;
    } catch (err) {
        log(`更新索引失敗: ${err.message}`, 'error');
        return false;
    }
}

/**
 * 移動資料夾 (含所有內容)
 */
function moveFolder(source, destination) {
    try {
        // 確保來源存在
        if (!fs.existsSync(source)) {
            log(`來源資料夾不存在: ${source}`, 'error');
            return false;
        }
        
        // 確保目標目錄的父層存在
        ensureDir(path.dirname(destination));
        
        // 如果目標已存在，先刪除
        if (fs.existsSync(destination)) {
            fs.rmSync(destination, { recursive: true, force: true });
            log(`覆蓋已存在的目標資料夾`, 'warn');
        }
        
        // 使用 rename 移動 (同一磁碟機更快)
        try {
            fs.renameSync(source, destination);
            return true; // 成功就直接返回
        } catch (renameErr) {
            // rename 失敗時，先確認來源是否還存在
            if (!fs.existsSync(source)) {
                // 來源不存在但目標存在，表示移動其實成功了
                if (fs.existsSync(destination)) {
                    log(`移動成功 (rename 報錯但實際成功)`, 'info');
                    return true;
                }
                log(`來源資料夾已消失: ${source}`, 'error');
                return false;
            }
            
            // 如果 rename 失敗 (跨磁碟機)，使用複製後刪除
            log(`使用複製模式移動 (rename 失敗: ${renameErr.message})`, 'info');
            copyFolderRecursive(source, destination);
            fs.rmSync(source, { recursive: true, force: true });
            return true;
        }
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
    
    // 0. 驗證路徑格式
    const pathValidation = validateAbsolutePath(folderPath);
    if (!pathValidation.valid) {
        log(`路徑錯誤: ${pathValidation.error}`, 'error');
        return false;
    }
    
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
    let successfulImports = 0;
    
    for (const pdfFile of pdfFiles) {
        // 正規化路徑
        const pdfPath = normalizePathForEagle(path.join(folderPath, pdfFile));
        
        // 再次驗證 PDF 路徑
        const pdfPathValidation = validateAbsolutePath(pdfPath);
        if (!pdfPathValidation.valid) {
            log(`PDF 路徑錯誤: ${pdfPathValidation.error}`, 'error');
            continue;
        }
        
        try {
            // 準備匯入選項
            const importOptions = {};
            if (metadata) {
                if (metadata.name) importOptions.name = metadata.name;
                if (metadata.url) importOptions.website = metadata.url;
                if (metadata.tags && Array.isArray(metadata.tags)) importOptions.tags = metadata.tags;
                if (metadata.annotation) importOptions.annotation = metadata.annotation;
            }
            
            // addFromPath 需要普通路徑字串，不是 file:// URL
            log(`匯入 PDF: ${pdfFile}`, 'info');
            if (CONFIG.DEBUG) {
                log(`完整路徑: ${pdfPath}`, 'info');
                log(`選項: ${JSON.stringify(importOptions)}`, 'info');
            }
            
            // 使用 Eagle API 匯入檔案 (帶 metadata)
            const itemId = await eagle.item.addFromPath(pdfPath, importOptions);
            
            if (itemId) {
                log(`匯入成功, ID: ${itemId}`, 'success');
                successfulImports++;
                
                // 重新生成縮圖，確保 Eagle 正確識別為 PDF 文件
                // 這樣點擊時會使用 PDF 閱讀模式而不是圖片瀏覽模式
                try {
                    const item = await eagle.item.getById(itemId);
                    if (item) {
                        await item.refreshThumbnail();
                        log(`已刷新縮圖: ${pdfFile}`, 'info');
                        
                        // 儲存到匯入索引 (供 Discord Bot 使用)
                        addToImportsIndex(folderName, itemId, item.filePath, metadata);
                    }
                } catch (refreshErr) {
                    log(`刷新縮圖失敗: ${refreshErr.message}`, 'warn');
                }
                
                importedCount++;
                updateStatsUI();
            } else {
                log(`匯入失敗 (無 itemId): ${pdfFile}`, 'error');
            }
        } catch (err) {
            log(`匯入錯誤: ${pdfFile} - ${err.message}`, 'error');
            if (err.message.includes('absolute')) {
                log('💡 提示: 請確認已將 NAS 掛載為磁碟機 (如 Z:)', 'warn');
                log('   執行: net use Z: \\\\192.168.10.2\\docker', 'warn');
            }
            console.error('完整錯誤:', err);
        }
    }
    
    // 4. 只有在至少一個 PDF 匯入成功時才歸檔
    if (successfulImports === 0) {
        log(`跳過歸檔 (無成功匯入): ${folderName}`, 'warn');
        return false;
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
        // 驗證監控路徑格式
        const watchPathValidation = validateAbsolutePath(CONFIG.NAS_WATCH_PATH);
        if (!watchPathValidation.valid) {
            log(`⚠️ 監控路徑格式錯誤: ${watchPathValidation.error}`, 'error');
            log('請修改 CONFIG.NAS_WATCH_PATH 為映射磁碟機路徑 (如 Z:\\HentaiFetcher\\downloads)', 'warn');
            log('設定映射: net use Z: \\\\192.168.10.2\\docker', 'warn');
            isScanning = false;
            return;
        }
        
        // 確保監控路徑存在
        if (!fs.existsSync(CONFIG.NAS_WATCH_PATH)) {
            log(`監控路徑不存在: ${CONFIG.NAS_WATCH_PATH}`, 'error');
            log('請確認磁碟機已正確掛載', 'warn');
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
