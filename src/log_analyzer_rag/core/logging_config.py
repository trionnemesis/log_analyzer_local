"""Utility for configuring project-wide logging."""

import logging
import sys
from .config import settings

def setup_logging():
    """設定全域日誌記錄器"""
    log_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        # 使用 'a' 模式來附加日誌，而不是每次覆寫
        file_handler = logging.FileHandler(settings.LMS_OPERATIONAL_LOG_FILE, mode='a', encoding='utf-8')
        log_handlers.append(file_handler)
    except PermissionError:
        print(
            f"[CRITICAL] 無權限寫入運維日誌檔案 {settings.LMS_OPERATIONAL_LOG_FILE}。"
            "請檢查權限或更改 LMS_OPERATIONAL_LOG_FILE 環境變數。"
        )
    except Exception as e:
        print(f"[CRITICAL] 設定檔案日誌時發生錯誤: {e}")


    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        handlers=log_handlers
    )

    # 調整一些函式庫的日誌級別，避免過多雜訊
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
