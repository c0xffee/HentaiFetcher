#!/usr/bin/env python3
"""
PDF 線性化測試腳本 (階段 1)
===========================
測試 pikepdf 的兩種線性化功能：
1. 功能 1：用 Pillow 製作 PDF → pikepdf 線性化
2. 功能 2：現有 PDF → pikepdf 線性化

使用方式:
    python test_linearize.py
"""

import sys
import time
from pathlib import Path
from io import BytesIO

# 測試輸出目錄
TEST_OUTPUT_DIR = Path(__file__).parent / "test_linearize_output"
# 現有 PDF 測試來源
EXISTING_PDF_PATH = Path(__file__).parent / "downloads" / "198792" / "198792.pdf"
# 測試圖片來源 (使用現有下載資料夾的圖片)
TEST_IMAGES_DIR = Path(__file__).parent / "downloads" / "198792"


def check_dependencies():
    """檢查必要依賴"""
    print("=" * 60)
    print("🔍 檢查依賴...")
    print("=" * 60)
    
    missing = []
    
    try:
        import pikepdf
        print(f"✅ pikepdf 版本: {pikepdf.__version__}")
    except ImportError:
        print("❌ pikepdf 未安裝")
        missing.append("pikepdf")
    
    try:
        from PIL import Image
        import PIL
        print(f"✅ Pillow 版本: {PIL.__version__}")
    except ImportError:
        print("❌ Pillow 未安裝")
        missing.append("Pillow")
    
    if missing:
        print(f"\n⚠️  請先安裝缺少的套件:")
        print(f"   pip install {' '.join(missing)}")
        return False
    
    print()
    return True


def get_file_size_mb(path: Path) -> float:
    """取得檔案大小 (MB)"""
    return path.stat().st_size / (1024 * 1024)


def check_linearization(pdf_path: Path) -> bool:
    """檢查 PDF 是否已線性化"""
    import pikepdf
    
    try:
        with pikepdf.open(pdf_path) as pdf:
            return pdf.is_linearized
    except Exception as e:
        print(f"   ⚠️  無法檢查線性化狀態: {e}")
        return False


def test_function_1():
    """
    功能 1 測試：用 Pillow 製作 PDF → pikepdf 線性化
    模擬 Bot 下載流程
    """
    print("=" * 60)
    print("🧪 功能 1 測試：Pillow 製作 PDF → pikepdf 線性化")
    print("=" * 60)
    
    from PIL import Image
    import pikepdf
    
    # 尋找測試圖片
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    test_images = sorted([
        f for f in TEST_IMAGES_DIR.iterdir() 
        if f.suffix.lower() in image_extensions
    ])[:10]  # 只取前 10 張測試
    
    if not test_images:
        print("❌ 找不到測試圖片")
        return False
    
    print(f"📷 使用 {len(test_images)} 張圖片進行測試")
    
    # 確保輸出目錄存在
    TEST_OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Step 1: 讀取圖片並轉換為 RGB
    print("\n📖 Step 1: 讀取並處理圖片...")
    start_time = time.time()
    
    pil_images = []
    max_width = 0
    
    for img_path in test_images:
        img = Image.open(img_path)
        # 轉換為 RGB
        if img.mode in ('RGBA', 'P', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
                img = background
            else:
                img = img.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        pil_images.append(img)
        if img.width > max_width:
            max_width = img.width
    
    print(f"   統一寬度: {max_width}px")
    
    # Step 2: 調整為等寬
    resized_images = []
    for img in pil_images:
        if img.width != max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            resized_img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            resized_images.append(resized_img)
        else:
            resized_images.append(img)
    
    # Step 3: 存入 BytesIO (記憶體中的 PDF)
    print("📝 Step 2: 將圖片轉換為 PDF (記憶體)...")
    buffer = BytesIO()
    
    first_image = resized_images[0]
    rest_images = resized_images[1:] if len(resized_images) > 1 else []
    
    first_image.save(
        buffer,
        "PDF",
        save_all=True,
        append_images=rest_images,
        resolution=100.0
    )
    buffer.seek(0)
    
    buffer_size = len(buffer.getvalue()) / (1024 * 1024)
    print(f"   記憶體 PDF 大小: {buffer_size:.2f} MB")
    
    # Step 4: 使用 pikepdf 線性化
    print("⚡ Step 3: 使用 pikepdf 線性化...")
    
    output_path = TEST_OUTPUT_DIR / "test_function1_linearized.pdf"
    
    with pikepdf.open(buffer) as pdf:
        pdf.save(output_path, linearize=True)
    
    elapsed = time.time() - start_time
    
    # 驗證結果
    is_linearized = check_linearization(output_path)
    file_size = get_file_size_mb(output_path)
    
    print(f"\n✅ 功能 1 測試完成!")
    print(f"   輸出檔案: {output_path}")
    print(f"   檔案大小: {file_size:.2f} MB")
    print(f"   已線性化: {'✅ 是' if is_linearized else '❌ 否'}")
    print(f"   處理時間: {elapsed:.2f} 秒")
    
    # 清理記憶體
    for img in pil_images:
        img.close()
    for img in resized_images:
        try:
            img.close()
        except:
            pass
    
    return is_linearized


def test_function_2():
    """
    功能 2 測試：現有 PDF → pikepdf 線性化
    """
    print("\n" + "=" * 60)
    print("🧪 功能 2 測試：現有 PDF → pikepdf 線性化")
    print("=" * 60)
    
    import pikepdf
    
    if not EXISTING_PDF_PATH.exists():
        print(f"❌ 找不到測試 PDF: {EXISTING_PDF_PATH}")
        return False
    
    original_size = get_file_size_mb(EXISTING_PDF_PATH)
    original_linearized = check_linearization(EXISTING_PDF_PATH)
    
    print(f"📄 來源 PDF: {EXISTING_PDF_PATH}")
    print(f"   原始大小: {original_size:.2f} MB")
    print(f"   原始線性化狀態: {'✅ 是' if original_linearized else '❌ 否'}")
    
    # 確保輸出目錄存在
    TEST_OUTPUT_DIR.mkdir(exist_ok=True)
    
    output_path = TEST_OUTPUT_DIR / "test_function2_linearized.pdf"
    
    print("\n⚡ 開始線性化...")
    start_time = time.time()
    
    with pikepdf.open(EXISTING_PDF_PATH) as pdf:
        pdf.save(output_path, linearize=True)
    
    elapsed = time.time() - start_time
    
    # 驗證結果
    is_linearized = check_linearization(output_path)
    new_size = get_file_size_mb(output_path)
    size_diff = new_size - original_size
    size_diff_percent = (size_diff / original_size) * 100 if original_size > 0 else 0
    
    print(f"\n✅ 功能 2 測試完成!")
    print(f"   輸出檔案: {output_path}")
    print(f"   新檔案大小: {new_size:.2f} MB")
    print(f"   大小變化: {size_diff:+.2f} MB ({size_diff_percent:+.1f}%)")
    print(f"   已線性化: {'✅ 是' if is_linearized else '❌ 否'}")
    print(f"   處理時間: {elapsed:.2f} 秒")
    
    return is_linearized


def main():
    """主程式"""
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " PDF 線性化測試 (階段 1)".center(56) + " ║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    # 檢查依賴
    if not check_dependencies():
        sys.exit(1)
    
    # 執行測試
    result1 = test_function_1()
    result2 = test_function_2()
    
    # 總結
    print("\n" + "=" * 60)
    print("📊 測試總結")
    print("=" * 60)
    print(f"   功能 1 (Pillow → pikepdf): {'✅ 成功' if result1 else '❌ 失敗'}")
    print(f"   功能 2 (現有 PDF 線性化): {'✅ 成功' if result2 else '❌ 失敗'}")
    print()
    print(f"📁 測試輸出目錄: {TEST_OUTPUT_DIR}")
    print()
    
    if result1 and result2:
        print("🎉 所有測試通過！可以進行效能測試。")
        print()
        print("📌 下一步驟:")
        print("   1. 使用瀏覽器開啟測試 PDF，比較載入速度")
        print("   2. 使用 qpdf --show-linearization 驗證結構")
        print("   3. 確認後進入階段 2")
    else:
        print("⚠️  部分測試失敗，請檢查錯誤訊息。")
    
    print()
    return 0 if (result1 and result2) else 1


if __name__ == "__main__":
    sys.exit(main())
