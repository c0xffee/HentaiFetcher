"""
HentaiFetcher Services Module
=============================
業務邏輯服務層
"""

from .nhentai_api import (
    verify_nhentai_url,
    get_nhentai_page_count,
    fetch_nhentai_extra_info,
    download_nhentai_cover,
    download_nhentai_first_page,
)

from .metadata_service import (
    parse_gallery_dl_info,
    create_eagle_metadata,
    find_info_json,
)

from .index_service import (
    quick_reindex,
    check_already_downloaded,
    get_all_downloads_items,
    find_item_by_id,
    search_in_downloads,
    get_random_gallery_id,
    get_random_from_downloads,
    parse_annotation_comments,
)

__all__ = [
    # nhentai_api
    'verify_nhentai_url',
    'get_nhentai_page_count',
    'fetch_nhentai_extra_info',
    'download_nhentai_cover',
    'download_nhentai_first_page',
    # metadata_service
    'parse_gallery_dl_info',
    'create_eagle_metadata',
    'find_info_json',
    # index_service
    'quick_reindex',
    'check_already_downloaded',
    'get_all_downloads_items',
    'find_item_by_id',
    'search_in_downloads',
    'get_random_gallery_id',
    'get_random_from_downloads',
    'parse_annotation_comments',
]
