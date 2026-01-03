# ============================================
# HentaiFetcher Docker Image
# ============================================
# 基於 Python 3.9 slim 的自動化漫畫下載器
# 包含 Discord Bot、gallery-dl、aria2、img2pdf
# ============================================

FROM python:3.9-slim

# 設定環境變數
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴
# - gcc/build-essential: 編譯某些 Python 套件需要
# - libffi-dev: discord.py 依賴
# - libjpeg-dev, zlib1g-dev, libpng-dev: 圖片處理依賴
# - ffmpeg: gallery-dl 某些功能可能需要
# - aria2: 多線程下載工具，與 gallery-dl 配合使用
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    ffmpeg \
    aria2 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 安裝 Python 依賴
RUN pip install --no-cache-dir \
    discord.py>=2.3.0 \
    gallery-dl>=1.26.0 \
    img2pdf>=0.5.0 \
    Pillow>=10.0.0 \
    pikepdf>=8.0.0

# 建立必要目錄
RUN mkdir -p /app/config /app/downloads /app/temp /app/bot/views

# 複製應用程式碼
COPY run.py /app/run.py
COPY eagle_library.py /app/eagle_library.py
COPY bot/ /app/bot/

# 設定權限
RUN chmod +x /app/run.py

# 設定 gallery-dl 配置目錄
ENV GALLERY_DL_CONFIG=/app/config/gallery-dl.conf

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import discord; print('OK')" || exit 1

# 啟動指令
CMD ["python", "-u", "/app/run.py"]
