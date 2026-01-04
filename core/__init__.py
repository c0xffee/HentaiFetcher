"""
HentaiFetcher Core Module
=========================
核心功能模組，包含配置、下載處理器、佇列管理等
"""

from .config import (
    VERSION,
    IS_DOCKER,
    BASE_DIR,
    CONFIG_DIR,
    DOWNLOAD_DIR,
    TEMP_DIR,
    IMPORTED_DIR,
    logger,
    PROGRESS_UPDATE_INTERVAL,
    SECONDS_PER_PAGE,
    PROGRESS_BAR_WIDTH,
    PDF_WEB_BASE_URL,
    DEDICATED_CHANNEL_NAMES,
    DEDICATED_CHANNEL_IDS,
    MAX_PROCESSED_MESSAGES,
    REINDEX_COOLDOWN,
    print_startup_info,
)

from .batch_manager import (
    download_queue,
    cancel_events,
    batch_tracker,
    request_cancel,
    register_cancel_event,
    unregister_cancel_event,
    is_cancelled,
    generate_batch_id,
    init_batch,
    update_batch,
    is_message_processed,
    get_queue_size,
    add_to_queue,
)

__all__ = [
    # config
    'VERSION',
    'IS_DOCKER',
    'BASE_DIR',
    'CONFIG_DIR',
    'DOWNLOAD_DIR',
    'TEMP_DIR',
    'IMPORTED_DIR',
    'logger',
    'PROGRESS_UPDATE_INTERVAL',
    'SECONDS_PER_PAGE',
    'PROGRESS_BAR_WIDTH',
    'PDF_WEB_BASE_URL',
    'DEDICATED_CHANNEL_NAMES',
    'DEDICATED_CHANNEL_IDS',
    'MAX_PROCESSED_MESSAGES',
    'REINDEX_COOLDOWN',
    'print_startup_info',
    # batch_manager
    'download_queue',
    'cancel_events',
    'batch_tracker',
    'request_cancel',
    'register_cancel_event',
    'unregister_cancel_event',
    'is_cancelled',
    'generate_batch_id',
    'init_batch',
    'update_batch',
    'is_message_processed',
    'get_queue_size',
    'add_to_queue',
]
