#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher Download Processor
================================
下載處理器：負責執行 gallery-dl、轉換 PDF 並生成 metadata
"""

import re
import sys
import json
import time
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import quote

from core.config import (
    VERSION, IS_DOCKER, BASE_DIR, DOWNLOAD_DIR, TEMP_DIR, 
    logger, PDF_WEB_BASE_URL
)
from utils.helpers import sanitize_filename, find_images
from services.metadata_service import parse_gallery_dl_info, create_eagle_metadata, find_info_json
from services.nhentai_api import fetch_nhentai_extra_info


class DownloadProcessor:
    """
    下載處理器：負責執行 gallery-dl、轉換 PDF 並生成 metadata
    """
    
    def __init__(self, url: str, total_pages: int = 0, message_callback=None, cancel_event: threading.Event = None):
        """
        初始化下載處理器
        
        Args:
            url: 要下載的網址
            total_pages: 預期總頁數（用於進度計算）
            message_callback: 狀態更新回調函式
            cancel_event: 取消事件（被 set 時應中止下載）
        """
        self.url = url
        self.total_pages = total_pages
        self.message_callback = message_callback
        self.cancel_event = cancel_event
        self.temp_path: Optional[Path] = None
        self.output_path: Optional[Path] = None
        self.last_error: str = ""
        self.download_complete = False  # 下載是否完成
        self.pdf_progress = 0  # PDF 轉換進度 (0-100)
        self.pdf_converting = False  # 是否正在轉換 PDF
    
    def is_cancelled(self) -> bool:
        """檢查是否已被取消"""
        return self.cancel_event and self.cancel_event.is_set()
        
    def get_downloaded_count(self) -> int:
        """獲取已下載的圖片數量"""
        if not self.temp_path or not self.temp_path.exists():
            return 0
        return len(find_images(self.temp_path))
    
    def get_first_image_path(self) -> Path:
        """獲取第一張已下載圖片的路徑"""
        if not self.temp_path or not self.temp_path.exists():
            return None
        images = find_images(self.temp_path)
        if images:
            # 按檔名排序取第一張
            images.sort(key=lambda x: x.name)
            return images[0]
        return None
        
    async def send_status(self, message: str):
        """發送狀態訊息"""
        logger.info(message)
        if self.message_callback:
            try:
                await self.message_callback(message)
            except Exception as e:
                logger.warning(f"無法發送狀態訊息: {e}")
    
    def download_with_gallery_dl(self) -> bool:
        """
        使用 gallery-dl 下載圖片和 metadata
        
        Returns:
            成功返回 True，失敗返回 False
        """
        try:
            # 建立唯一的暫存目錄（統一使用 TEMP_DIR）
            self.temp_path = TEMP_DIR / f"dl_{int(time.time() * 1000)}"
            self.temp_path.mkdir(parents=True, exist_ok=True)
            
            print(f"[GALLERY-DL] 下載目錄: {self.temp_path}", flush=True)
            
            # 根據環境選擇 gallery-dl 執行方式與參數
            if IS_DOCKER:
                # Docker 環境：兩階段下載
                # 階段 1: 使用 gallery-dl --dump-json 獲取 metadata
                print(f"[GALLERY-DL] 階段1: 獲取 metadata...", flush=True)
                metadata_cmd = [
                    'gallery-dl',
                    '--dump-json',
                    '--user-agent', 'Mozilla/5.0',
                    self.url
                ]
                
                metadata_result = subprocess.run(
                    metadata_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                # 解析並儲存 metadata
                if metadata_result.returncode == 0 and metadata_result.stdout.strip():
                    try:
                        # gallery-dl --dump-json 輸出的是 JSON 陣列
                        metadata_list = json.loads(metadata_result.stdout)
                        if metadata_list and len(metadata_list) > 0:
                            # 取第一個元素的 metadata（通常包含 gallery info）
                            first_item = metadata_list[0]
                            if isinstance(first_item, list) and len(first_item) >= 2:
                                gallery_metadata = first_item[1]  # [url, metadata] 格式
                            else:
                                gallery_metadata = first_item
                            
                            # 儲存 metadata 到暫存目錄
                            metadata_file = self.temp_path / "gallery_metadata.json"
                            with open(metadata_file, 'w', encoding='utf-8') as f:
                                json.dump(gallery_metadata, f, ensure_ascii=False, indent=2)
                            print(f"[GALLERY-DL] Metadata 已儲存: {metadata_file}", flush=True)
                    except json.JSONDecodeError as e:
                        print(f"[GALLERY-DL] Metadata 解析失敗: {e}", flush=True)
                
                # 階段 2: 使用 gallery-dl -g + aria2c 多線程下載圖片
                print(f"[GALLERY-DL] 階段2: 多線程下載圖片...", flush=True)
                cmd = (
                    f'gallery-dl --user-agent "Mozilla/5.0" -g "{self.url}" | '
                    f'aria2c -i - -x 8 -s 8 --user-agent="Mozilla/5.0" -d "{self.temp_path}"'
                )
                
                logger.info(f"執行指令: {cmd}")
                print(f"[GALLERY-DL+ARIA2] 命令: {cmd}", flush=True)
                
                # 使用 shell=True 執行管道命令
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=900
                )
            else:
                # Windows 環境：兩階段下載
                # 階段 1: 使用 gallery-dl --dump-json 獲取 metadata
                print(f"[GALLERY-DL] 階段1: 獲取 metadata...", flush=True)
                metadata_cmd = [
                    sys.executable,
                    '-m', 'gallery_dl',
                    '--dump-json',
                    self.url
                ]
                
                metadata_result = subprocess.run(
                    metadata_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                # 解析並儲存 metadata
                if metadata_result.returncode == 0 and metadata_result.stdout.strip():
                    try:
                        metadata_list = json.loads(metadata_result.stdout)
                        if metadata_list and len(metadata_list) > 0:
                            first_item = metadata_list[0]
                            if isinstance(first_item, list) and len(first_item) >= 2:
                                gallery_metadata = first_item[1]
                            else:
                                gallery_metadata = first_item
                            
                            metadata_file = self.temp_path / "gallery_metadata.json"
                            with open(metadata_file, 'w', encoding='utf-8') as f:
                                json.dump(gallery_metadata, f, ensure_ascii=False, indent=2)
                            print(f"[GALLERY-DL] Metadata 已儲存: {metadata_file}", flush=True)
                    except json.JSONDecodeError as e:
                        print(f"[GALLERY-DL] Metadata 解析失敗: {e}", flush=True)
                
                # 階段 2: 下載圖片
                print(f"[GALLERY-DL] 階段2: 下載圖片...", flush=True)
                
                # 設定檔路徑
                config_path = BASE_DIR / "config" / "gallery-dl.conf"
                
                cmd = [
                    sys.executable,
                    '-m', 'gallery_dl',
                    '--config', str(config_path),
                    '--dest', str(self.temp_path),
                    '--write-metadata',
                    self.url
                ]
                
                logger.info(f"執行指令: {' '.join(cmd)}")
                print(f"[GALLERY-DL] 命令: {cmd}", flush=True)
                
                # 執行 gallery-dl 命令
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=900
                )
            print(f"[GALLERY-DL] 執行完成", flush=True)
            
            # 強制輸出所有 gallery-dl 日誌（用於除錯）
            print(f"[GALLERY-DL] URL: {self.url}", flush=True)
            print(f"[GALLERY-DL] 返回碼: {result.returncode}", flush=True)
            print(f"[GALLERY-DL] STDOUT: {result.stdout[:2000] if result.stdout else '(空)'}", flush=True)
            print(f"[GALLERY-DL] STDERR: {result.stderr[:2000] if result.stderr else '(空)'}", flush=True)
            
            if result.returncode != 0:
                logger.error(f"gallery-dl 返回碼: {result.returncode}")
                logger.error(f"gallery-dl STDERR: {result.stderr}")
                logger.error(f"gallery-dl STDOUT: {result.stdout}")
                
                # 儲存詳細錯誤訊息供 Discord 回報
                # cmd 在 Docker 環境是字串，Windows 環境是列表
                cmd_str = cmd if isinstance(cmd, str) else ' '.join(cmd)
                error_lines = [
                    f"⚠️ **Debug 資訊**",
                    f"📦 版本: {VERSION}",
                    f"💻 環境: {'Docker' if IS_DOCKER else 'Windows'}",
                    f"📂 下載目錄: `{self.temp_path}`",
                    f"🔧 執行命令: `{cmd_str}`",
                    f"🔴 返回碼: {result.returncode}",
                ]
                
                if result.stderr:
                    error_lines.append(f"\n**STDERR:**\n```\n{result.stderr[:800]}\n```")
                if result.stdout:
                    error_lines.append(f"\n**STDOUT:**\n```\n{result.stdout[:800]}\n```")
                
                self.last_error = "\n".join(error_lines)
                return False
            
            logger.info(f"gallery-dl 輸出: {result.stdout}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("gallery-dl 執行超時")
            return False
        except Exception as e:
            logger.error(f"gallery-dl 執行錯誤: {e}")
            return False
    
    def convert_to_pdf(self, images: List[Path], output_pdf: Path) -> bool:
        """
        使用 Pillow 將圖片轉換為等寬 PDF（支援進度回報 + 線性化）
        
        所有圖片會被調整為統一寬度（使用最大寬度），高度按比例縮放，
        確保 PDF 每一頁都是 100% 寬度對齊。
        最後使用 pikepdf 線性化，加速網頁存取 (Fast Web View)。
        
        Args:
            images: 圖片檔案列表
            output_pdf: 輸出 PDF 路徑
        
        Returns:
            成功返回 True，失敗返回 False
        """
        if not images:
            logger.error("沒有圖片可供轉換")
            return False
        
        try:
            from PIL import Image
            from io import BytesIO
            import pikepdf
            
            self.pdf_converting = True
            self.pdf_progress = 0
            
            # 確保輸出目錄存在
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"轉換 {len(images)} 張圖片為等寬 PDF (含線性化)")
            
            total = len(images)
            
            # 階段 1: 讀取所有圖片並找出最大寬度 (0-20%)
            logger.info("階段 1/4: 分析圖片尺寸...")
            pil_images = []
            max_width = 0
            
            for i, img_path in enumerate(images):
                img = Image.open(img_path)
                # 轉換為 RGB（PDF 不支援 RGBA 透明通道）
                if img.mode in ('RGBA', 'P', 'LA'):
                    # 建立白色背景
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    if img.mode in ('RGBA', 'LA'):
                        background.paste(img, mask=img.split()[-1])  # 使用 alpha 通道作為遮罩
                        img = background
                    else:
                        img = img.convert('RGB')
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                pil_images.append(img)
                if img.width > max_width:
                    max_width = img.width
                
                self.pdf_progress = int((i + 1) / total * 20)
                if (i + 1) % 10 == 0:
                    time.sleep(0.05)
            
            logger.info(f"統一寬度: {max_width}px")
            
            # 階段 2: 調整所有圖片為等寬 (20-60%)
            logger.info("階段 2/4: 調整圖片為等寬...")
            resized_images = []
            
            for i, img in enumerate(pil_images):
                if img.width != max_width:
                    # 按比例縮放到目標寬度
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    # 使用高品質縮放
                    resized_img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    resized_images.append(resized_img)
                else:
                    resized_images.append(img)
                
                self.pdf_progress = 20 + int((i + 1) / total * 40)
                if (i + 1) % 10 == 0:
                    time.sleep(0.05)
            
            # 階段 3: 生成 PDF 到記憶體 (60-80%)
            logger.info("階段 3/4: 生成 PDF 到記憶體...")
            self.pdf_progress = 65
            
            # 第一張圖片作為基底，其餘 append
            first_image = resized_images[0]
            rest_images = resized_images[1:] if len(resized_images) > 1 else []
            
            # 先存到 BytesIO
            pdf_buffer = BytesIO()
            try:
                first_image.save(
                    pdf_buffer,
                    "PDF",
                    save_all=True,
                    append_images=rest_images,
                    resolution=100.0
                )
                pdf_buffer.seek(0)
                logger.info(f"PDF 記憶體大小: {len(pdf_buffer.getvalue()) / (1024*1024):.2f} MB")
            except Exception as save_error:
                logger.error(f"PDF save 失敗: {save_error}")
                import traceback
                logger.error(traceback.format_exc())
                self.pdf_converting = False
                return False
            
            self.pdf_progress = 80
            
            # 階段 4: 使用 pikepdf 線性化 (80-100%)
            logger.info("階段 4/4: PDF 線性化 (Fast Web View)...")
            try:
                with pikepdf.open(pdf_buffer) as pdf:
                    pdf.save(output_pdf, linearize=True)
                logger.info("PDF 線性化完成")
            except Exception as linearize_error:
                logger.warning(f"線性化失敗，改用非線性化存檔: {linearize_error}")
                # 失敗時直接存檔（不線性化）
                pdf_buffer.seek(0)
                with open(output_pdf, 'wb') as f:
                    f.write(pdf_buffer.getvalue())
            
            # 清理記憶體 - 使用 set 追蹤已關閉的圖片 id，避免比較操作
            closed_ids = set()
            for img in pil_images:
                if id(img) not in closed_ids:
                    try:
                        img.close()
                    except Exception:
                        pass
                    closed_ids.add(id(img))
            for img in resized_images:
                if id(img) not in closed_ids:
                    try:
                        img.close()
                    except Exception:
                        pass
                    closed_ids.add(id(img))
            
            self.pdf_progress = 100
            self.pdf_converting = False
            
            # 確認 PDF 已生成
            if output_pdf.exists() and output_pdf.stat().st_size > 0:
                logger.info(f"PDF 生成成功: {output_pdf}")
                return True
            else:
                logger.error("PDF 檔案未生成或為空")
                return False
                
        except Exception as e:
            logger.error(f"PDF 轉換錯誤: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.pdf_converting = False
            return False
    
    def process(self) -> tuple:
        """
        執行完整的下載處理流程
        
        Returns:
            (成功狀態, 結果訊息)
        """
        start_time = time.time()  # 開始計時
        
        try:
            # 檢查是否已被取消
            if self.is_cancelled():
                return False, "🚫 下載已取消"
            
            # 步驟 1: 下載
            logger.info(f"開始下載: {self.url}")
            print(f"[PROCESS] 開始下載: {self.url}", flush=True)
            if not self.download_with_gallery_dl():
                # 再次檢查是否被取消
                if self.is_cancelled():
                    return False, "🚫 下載已取消"
                error_detail = self.last_error if self.last_error else "未知原因"
                elapsed = time.time() - start_time
                return False, f"❌ 下載失敗\n🔗 {self.url}\n⏱️ 耗時: {elapsed:.1f}s\n\n{error_detail}"
            
            # 檢查是否已被取消
            if self.is_cancelled():
                return False, "🚫 下載已取消"
            
            # 尋找下載的內容
            # gallery-dl 可能會建立子目錄
            print(f"[PROCESS] 搜尋圖片目錄: {self.temp_path}", flush=True)
            images = find_images(self.temp_path)
            print(f"[PROCESS] 找到 {len(images)} 張圖片", flush=True)
            
            if not images:
                # 列出目錄內容以便除錯
                try:
                    all_files = list(self.temp_path.rglob('*'))
                    print(f"[DEBUG] 目錄內所有檔案: {[str(f) for f in all_files[:20]]}", flush=True)
                except Exception as e:
                    print(f"[DEBUG] 無法列出目錄: {e}", flush=True)
                elapsed = time.time() - start_time
                return False, f"❌ 找不到下載的圖片\n🔗 {self.url}\n⏱️ 耗時: {elapsed:.1f}s"
            
            logger.info(f"找到 {len(images)} 張圖片")
            
            # 步驟 2: 解析 metadata
            info_json = find_info_json(self.temp_path)
            
            if info_json:
                metadata = parse_gallery_dl_info(info_json)
            else:
                logger.warning("找不到 info.json，使用預設 metadata")
                metadata = None
            
            # 設定標題 - 優先使用日文標題
            if metadata:
                # 優先順序: 日文標題 > 英文標題 > URL ID
                if metadata.get('title_japanese'):
                    title = metadata['title_japanese']
                    logger.info(f"使用日文標題: {title}")
                elif metadata.get('title'):
                    title = metadata['title']
                    logger.info(f"使用英文標題: {title}")
                else:
                    title = None
            else:
                title = None
            
            # 提取 gallery_id 用於目錄和檔名（避免路徑過長）
            gallery_id_for_path = metadata.get('gallery_id', '') if metadata else ''
            if not gallery_id_for_path:
                # 嘗試從 URL 提取
                match = re.search(r'/g/(\d+)', self.url)
                if match:
                    gallery_id_for_path = match.group(1)
                else:
                    gallery_id_for_path = str(int(time.time()))
            
            if not title:
                title = f"Gallery_{gallery_id_for_path}"
            
            safe_title = sanitize_filename(title)
            logger.info(f"使用標題: {safe_title}")
            logger.info(f"使用 Gallery ID 作為目錄名: {gallery_id_for_path}")
            
            # 建立輸出資料夾 - 使用 gallery_id 避免路徑過長
            self.output_path = DOWNLOAD_DIR / gallery_id_for_path
            
            # 如果資料夾已存在，使用時間戳命名避免覆蓋
            if self.output_path.exists():
                self.output_path = DOWNLOAD_DIR / f"{gallery_id_for_path}_{int(time.time())}"
                logger.info(f"資料夾已存在，使用新資料夾 {self.output_path}")
            
            self.output_path.mkdir(parents=True, exist_ok=True)
            
            # 步驟 3: 轉換為 PDF - 使用 gallery_id 作為檔名
            pdf_path = self.output_path / f"{gallery_id_for_path}.pdf"
            if not self.convert_to_pdf(images, pdf_path):
                return False, "❌ PDF 轉換失敗"
            
            # 步驟 3.5: 複製第一張圖片作為封面
            if images:
                try:
                    first_image = images[0]
                    # 獲取副檔名
                    ext = first_image.suffix  # 例如 .jpg, .png
                    cover_path = self.output_path / f"cover{ext}"
                    # 複製第一張圖片
                    shutil.copy2(first_image, cover_path)
                    logger.info(f"封面已保存: {cover_path.name}")
                except Exception as e:
                    logger.warning(f"保存封面失敗: {e}")
            
            # 步驟 4: 獲取額外資訊（收藏數、評論）
            gallery_id = metadata.get('gallery_id', '') if metadata else ''
            if not gallery_id:
                # 嘗試從 URL 提取
                match = re.search(r'/g/(\d+)', self.url)
                if match:
                    gallery_id = match.group(1)
            
            nhentai_extra = {}
            if gallery_id:
                logger.info(f"獲取 nhentai 額外資訊 (ID: {gallery_id})...")
                nhentai_extra = fetch_nhentai_extra_info(gallery_id)
            
            # 步驟 5: 生成 Eagle metadata（包含擴展資訊）
            extra_info = None
            if metadata:
                extra_info = {
                    'title_japanese': metadata.get('title_japanese', ''),
                    'title_english': metadata.get('title', ''),  # 英文標題放 annotation
                    'title_pretty': metadata.get('title_pretty', ''),
                    'gallery_id': metadata.get('gallery_id', ''),
                    'pages': metadata.get('pages', 0),
                    'favorites': nhentai_extra.get('favorites', 0),  # 從 API 獲取
                    'category': metadata.get('category', ''),
                    'type': metadata.get('type', ''),
                    'artist': metadata.get('artist', []),
                    'group': metadata.get('group', []),
                    'parody': metadata.get('parody', []),
                    'character': metadata.get('character', []),
                    'language': metadata.get('language', ''),
                    'comments': nhentai_extra.get('comments', []),  # 評論
                }
            
            eagle_metadata = create_eagle_metadata(
                title=title,  # 已經是日文標題優先
                url=metadata.get('url', self.url) if metadata else self.url,
                tags=metadata.get('tags', []) if metadata else [],
                annotation="",
                extra_info=extra_info
            )
            
            # 確保輸出目錄存在（防止 UNC 路徑問題）
            self.output_path.mkdir(parents=True, exist_ok=True)
            
            metadata_path = self.output_path / "metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(eagle_metadata, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Eagle metadata 已生成: {metadata_path}")
            
            # 步驟 5: 清理暫存檔案
            if self.temp_path and self.temp_path.exists():
                shutil.rmtree(self.temp_path)
                logger.info(f"已清理暫存目錄: {self.temp_path}")
            
            # 計算耗時
            elapsed = time.time() - start_time
            if elapsed >= 60:
                elapsed_str = f"{int(elapsed // 60)}分{int(elapsed % 60)}秒"
            else:
                elapsed_str = f"{elapsed:.1f}秒"
            
            # 獲取頁數
            page_count = metadata.get('pages', len(images)) if metadata else len(images)
            
            # 轉換路徑為字串，確保 UNC 路徑正確顯示
            output_path_str = str(self.output_path)
            if output_path_str.startswith('\\\\'):
                output_path_str = output_path_str  # 已經是正確的 UNC 路徑
            elif output_path_str.startswith('\\') and not output_path_str.startswith('\\\\'):
                output_path_str = '\\' + output_path_str  # 補上缺少的斜線
            
            # 生成 PDF Web 連結 - 使用實際資料夾名稱（可能有時間戳後綴）
            folder_name = self.output_path.name  # 使用實際資料夾名稱
            pdf_filename = f"{gallery_id_for_path}.pdf"
            pdf_web_url = f"{PDF_WEB_BASE_URL}/{quote(folder_name)}/{quote(pdf_filename)}"
            
            # 使用純 URL 顯示（避免 markdown 連結被編碼的括號破壞）
            return True, f"✅ 完成: **{safe_title}**\n📄 {page_count}頁 ⏱️ {elapsed_str}\n📥 {pdf_web_url}\n📁 {output_path_str}"
            
        except Exception as e:
            logger.exception(f"處理過程發生錯誤: {e}")
            
            # 計算耗時
            elapsed = time.time() - start_time
            
            # 清理暫存檔案
            if self.temp_path and self.temp_path.exists():
                try:
                    shutil.rmtree(self.temp_path)
                except Exception:
                    pass
            
            return False, f"❌ 錯誤: {str(e)}\n⏱️ 耗時: {elapsed:.1f}s"
