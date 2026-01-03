#!/usr/bin/env python3
"""
現存 PDF 線性化腳本 (階段 2)
=============================
掃描 downloads/ 和 imported/ 資料夾，將所有 PDF 線性化。

使用方式:
    python linearize_existing.py              # 預覽模式 (不修改檔案)
    python linearize_existing.py --execute    # 執行模式 (覆寫原檔)
    python linearize_existing.py --backup     # 執行前備份原檔

選項:
    --execute   實際執行線性化並覆寫原檔
    --backup    執行前備份原檔為 .pdf.bak
    --downloads 只處理 downloads 資料夾
    --imported  只處理 imported 資料夾
"""

import sys
import time
import argparse
from pathlib import Path
from typing import List, Tuple
from datetime import datetime

# 設定
BASE_DIR = Path(__file__).parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
IMPORTED_DIR = BASE_DIR / "imported"
EAGLE_LIBRARY_DIR = Path(r"\\192.168.10.2\docker\Eagle\nHentai.library\images")


def get_file_size_mb(path: Path) -> float:
    """取得檔案大小 (MB)"""
    try:
        return path.stat().st_size / (1024 * 1024)
    except:
        return 0.0


def find_all_pdfs(directories: List[Path]) -> List[Path]:
    """遞迴搜尋所有 PDF 檔案"""
    pdfs = []
    for directory in directories:
        if directory.exists():
            pdfs.extend(directory.rglob("*.pdf"))
    return sorted(pdfs)


def check_linearization(pdf_path: Path) -> Tuple[bool, str]:
    """
    檢查 PDF 是否已線性化
    
    Returns:
        (is_linearized, error_message)
    """
    import pikepdf
    
    try:
        with pikepdf.open(pdf_path) as pdf:
            return pdf.is_linearized, ""
    except Exception as e:
        return False, str(e)


def linearize_pdf(pdf_path: Path, backup: bool = False) -> Tuple[bool, str, float]:
    """
    線性化 PDF 檔案
    
    Args:
        pdf_path: PDF 檔案路徑
        backup: 是否備份原檔
    
    Returns:
        (success, message, elapsed_seconds)
    """
    import pikepdf
    
    try:
        start_time = time.time()
        
        # 備份原檔
        if backup:
            backup_path = pdf_path.with_suffix('.pdf.bak')
            if not backup_path.exists():
                import shutil
                shutil.copy2(pdf_path, backup_path)
        
        # 讀取並線性化
        with pikepdf.open(pdf_path) as pdf:
            # 先存到臨時檔案
            temp_path = pdf_path.with_suffix('.pdf.tmp')
            pdf.save(temp_path, linearize=True)
        
        # 覆寫原檔
        temp_path.replace(pdf_path)
        
        elapsed = time.time() - start_time
        return True, "成功", elapsed
        
    except Exception as e:
        # 清理臨時檔案
        temp_path = pdf_path.with_suffix('.pdf.tmp')
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        return False, str(e), 0.0


def main():
    parser = argparse.ArgumentParser(description='現存 PDF 線性化腳本')
    parser.add_argument('--execute', action='store_true', help='實際執行線性化')
    parser.add_argument('--backup', action='store_true', help='執行前備份原檔')
    parser.add_argument('--downloads', action='store_true', help='只處理 downloads')
    parser.add_argument('--imported', action='store_true', help='只處理 imported')
    parser.add_argument('--eagle', action='store_true', help='只處理 Eagle Library')
    args = parser.parse_args()
    
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " 現存 PDF 線性化腳本 (階段 2)".center(52) + "   ║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # 決定要處理的目錄
    directories = []
    has_filter = args.downloads or args.imported or args.eagle
    
    if args.downloads or not has_filter:
        directories.append(DOWNLOADS_DIR)
    if args.imported or not has_filter:
        directories.append(IMPORTED_DIR)
    if args.eagle or not has_filter:
        directories.append(EAGLE_LIBRARY_DIR)
    
    print(f"📁 掃描目錄:")
    for d in directories:
        exists = "✅" if d.exists() else "❌"
        print(f"   {exists} {d}")
    print()
    
    # 檢查 pikepdf
    try:
        import pikepdf
        print(f"✅ pikepdf 版本: {pikepdf.__version__}")
    except ImportError:
        print("❌ pikepdf 未安裝，請執行: pip install pikepdf")
        return 1
    
    # 搜尋所有 PDF
    print("\n🔍 搜尋 PDF 檔案...")
    all_pdfs = find_all_pdfs(directories)
    
    if not all_pdfs:
        print("   找不到任何 PDF 檔案")
        return 0
    
    print(f"   找到 {len(all_pdfs)} 個 PDF 檔案")
    
    # 分析每個 PDF
    print("\n📊 分析線性化狀態...")
    
    already_linearized = []
    need_linearize = []
    errors = []
    total_size = 0.0
    
    for pdf in all_pdfs:
        size = get_file_size_mb(pdf)
        total_size += size
        is_linear, error = check_linearization(pdf)
        
        if error:
            errors.append((pdf, error))
        elif is_linear:
            already_linearized.append((pdf, size))
        else:
            need_linearize.append((pdf, size))
    
    # 顯示統計
    print(f"\n{'=' * 60}")
    print("📈 統計")
    print(f"{'=' * 60}")
    print(f"   總計: {len(all_pdfs)} 個 PDF ({total_size:.2f} MB)")
    print(f"   ✅ 已線性化: {len(already_linearized)} 個")
    print(f"   ⚡ 待處理: {len(need_linearize)} 個")
    if errors:
        print(f"   ❌ 錯誤: {len(errors)} 個")
    
    # 顯示待處理清單
    if need_linearize:
        need_size = sum(s for _, s in need_linearize)
        print(f"\n{'=' * 60}")
        print(f"⚡ 待線性化 ({len(need_linearize)} 個, {need_size:.2f} MB)")
        print(f"{'=' * 60}")
        
        # 按大小排序
        need_linearize.sort(key=lambda x: x[1], reverse=True)
        
        for pdf, size in need_linearize[:20]:  # 只顯示前 20 個
            rel_path = pdf.relative_to(BASE_DIR) if pdf.is_relative_to(BASE_DIR) else pdf
            print(f"   {size:>8.2f} MB  {rel_path}")
        
        if len(need_linearize) > 20:
            print(f"   ... 還有 {len(need_linearize) - 20} 個檔案")
    
    # 顯示錯誤
    if errors:
        print(f"\n{'=' * 60}")
        print(f"❌ 錯誤 ({len(errors)} 個)")
        print(f"{'=' * 60}")
        for pdf, error in errors[:10]:
            rel_path = pdf.relative_to(BASE_DIR) if pdf.is_relative_to(BASE_DIR) else pdf
            print(f"   {rel_path}: {error[:50]}")
    
    # 執行模式
    if not args.execute:
        print(f"\n{'=' * 60}")
        print("📌 預覽模式 (未修改任何檔案)")
        print(f"{'=' * 60}")
        print("   若要執行線性化，請加上 --execute 參數:")
        print("   python linearize_existing.py --execute")
        print("   python linearize_existing.py --execute --backup  # 備份原檔")
        print()
        return 0
    
    if not need_linearize:
        print("\n✅ 所有 PDF 已經線性化，無需處理")
        return 0
    
    # 執行線性化
    print(f"\n{'=' * 60}")
    print(f"⚡ 開始線性化 ({len(need_linearize)} 個檔案)")
    if args.backup:
        print("   📦 備份模式已啟用")
    print(f"{'=' * 60}")
    
    success_count = 0
    fail_count = 0
    total_time = 0.0
    
    for i, (pdf, size) in enumerate(need_linearize, 1):
        rel_path = pdf.relative_to(BASE_DIR) if pdf.is_relative_to(BASE_DIR) else pdf
        print(f"\n[{i}/{len(need_linearize)}] {rel_path} ({size:.2f} MB)")
        
        success, message, elapsed = linearize_pdf(pdf, backup=args.backup)
        total_time += elapsed
        
        if success:
            success_count += 1
            print(f"   ✅ {message} ({elapsed:.2f} 秒)")
        else:
            fail_count += 1
            print(f"   ❌ {message}")
    
    # 最終報告
    print(f"\n{'=' * 60}")
    print("📊 執行結果")
    print(f"{'=' * 60}")
    print(f"   ✅ 成功: {success_count} 個")
    print(f"   ❌ 失敗: {fail_count} 個")
    print(f"   ⏱️  總耗時: {total_time:.2f} 秒")
    if success_count > 0:
        print(f"   📈 平均: {total_time/success_count:.2f} 秒/檔案")
    print()
    
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
