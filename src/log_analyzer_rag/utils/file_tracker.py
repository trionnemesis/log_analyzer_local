"""File utilities for tracking log file read positions."""

import bz2
import gzip
import io
import json
import logging
from pathlib import Path
from typing import Dict, List, Any

from ..core.config import settings

logger = logging.getLogger(__name__)

FileState = Dict[str, Dict[str, Any]]

def load_log_state() -> FileState:
    """從 JSON 檔案載入日誌檔案的處理狀態"""
    if settings.LOG_STATE_FILE.exists():
        try:
            state = json.loads(settings.LOG_STATE_FILE.read_text(encoding='utf-8'))
            logger.info(f"從 {settings.LOG_STATE_FILE} 載入檔案狀態。")
            return state
        except Exception as e:
            logger.error(f"載入檔案狀態檔 {settings.LOG_STATE_FILE} 失敗: {e}。將使用空狀態。")
            return {}
    logger.info(f"未找到檔案狀態檔 {settings.LOG_STATE_FILE}，將使用空狀態。")
    return {}

def save_log_state(state: FileState):
    """將日誌檔案的處理狀態儲存至 JSON 檔案"""
    try:
        settings.LOG_STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')
        logger.debug(f"檔案狀態已儲存至 {settings.LOG_STATE_FILE}。")
    except Exception as e:
        logger.error(f"儲存檔案狀態至 {settings.LOG_STATE_FILE} 失敗: {e}")

STATE = load_log_state()

def open_log_file(path: Path) -> io.BufferedReader:
    """根據副檔名打開可能被壓縮的日誌檔案"""
    if path.suffix == ".gz":
        return gzip.open(path, "rb")  # type: ignore
    if path.suffix == ".bz2":
        return bz2.open(path, "rb")  # type: ignore
    return path.open("rb")

def tail_since(path: Path) -> List[str]:
    """從上次讀取的位置繼續讀取檔案的新增內容"""
    try:
        inode = path.stat().st_ino
    except FileNotFoundError:
        logger.warning(f"日誌檔案 {path} 不存在，跳過處理。")
        return []

    file_key = str(path.resolve())
    stored = STATE.get(file_key, {"inode": inode, "offset": 0})

    if stored["inode"] != inode:
        logger.info(f"日誌檔案 {path} inode 發生變化 (從 {stored['inode']} 到 {inode})，視為新檔案並從頭讀取。")
        stored = {"inode": inode, "offset": 0}

    new_lines: List[str] = []
    try:
        with open_log_file(path) as f:
            f.seek(stored["offset"])
            for line_bytes in f:
                try:
                    new_lines.append(line_bytes.decode("utf-8").rstrip())
                except UnicodeDecodeError:
                    decoded_line = line_bytes.decode("utf-8", "replace").rstrip()
                    logger.warning(f"檔案 {path} 中存在 Unicode 解碼錯誤。已使用 'replace' 處理。")
                    new_lines.append(decoded_line)
            stored["offset"] = f.tell()
    except Exception as e:
        logger.error(f"讀取日誌檔案 {path} 失敗: {e}")
        return []

    STATE[file_key] = stored
    if new_lines:
        logger.info(f"從 {path.name} 讀取到 {len(new_lines)} 行新日誌。目前 offset: {stored['offset']}")
    return new_lines
