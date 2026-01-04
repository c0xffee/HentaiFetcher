#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HentaiFetcher URL Parser
========================
URL 解析工具
"""

import re
from typing import List

from core.config import logger


def parse_input_to_urls(input_text: str) -> List[str]:
    """
    解析使用者輸入，支援多種格式：
    - 完整網址: https://nhentai.net/g/123456/
    - 純數字: 123456
    - 多個輸入（空白、逗號、換行分隔）
    - 混合輸入: 421633 https://nhentai.net/g/607769/ 613358
    
    Args:
        input_text: 使用者輸入的文字
    
    Returns:
        解析後的完整 URL 列表
    """
    urls = []
    
    # 標準化換行符號（處理 Windows/Mac/Linux 不同的換行）
    normalized_text = input_text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Debug 日誌
    logger.debug(f"原始輸入: {repr(input_text)}")
    logger.debug(f"標準化後: {repr(normalized_text)}")
    
    # 按行分割處理
    lines = normalized_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 每行可能有多個項目（空白或逗號分隔）
        parts = re.split(r'[\s,;]+', line)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 如果是完整 URL
            if part.startswith(('http://', 'https://')):
                # 清理 URL 結尾可能的標點符號
                url = part.rstrip('.,;')
                urls.append(url)
            # 如果是純數字
            elif part.isdigit():
                urls.append(f"https://nhentai.net/g/{part}/")
            # 嘗試提取數字（例如: g/123456 或 #123456）
            else:
                match = re.search(r'(\d{4,7})', part)
                if match:
                    urls.append(f"https://nhentai.net/g/{match.group(1)}/")
    
    # 去除重複並保持順序
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    
    logger.info(f"解析到 {len(unique_urls)} 個 URL")
    return unique_urls
