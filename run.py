"""CLI for running the log analysis pipeline."""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

# 從我們重構的模組中導入必要的元件
from src.log_analyzer_rag.core.config import settings
from src.log_analyzer_rag.core.logging_config import setup_logging
from src.log_analyzer_rag.main_process import process_and_analyze_logs
from src.log_analyzer_rag.rag_pipeline.llm import COST_TRACKER
from src.log_analyzer_rag.rag_pipeline.vector_store import VECTOR_DB
from src.log_analyzer_rag.utils.file_tracker import save_log_state, STATE

# 初始化日誌記錄器
setup_logging()
logger = logging.getLogger(__name__)


def find_log_files(target_dir: Path) -> List[Path]:
    """從目標目錄中尋找要處理的日誌檔案"""
    if not target_dir.exists() or not target_dir.is_dir():
        logger.warning(
            f"目標日誌目錄 {target_dir} 不存在或不是一個目錄。"
            "請建立該目錄並放入日誌檔案，或更改 LMS_TARGET_LOG_DIR 環境變數。"
        )
        return []

    logger.info(f"正在掃描日誌目錄: {target_dir}")
    log_files = [
        item for item in target_dir.iterdir()
        if item.is_file() and item.suffix.lower() in [".log", ".gz", ".bz2"]
    ]

    if not log_files:
        logger.info(f"在 {target_dir} 中未找到符合條件 (.log, .gz, .bz2) 的日誌檔案。")
    else:
        logger.info(f"將處理以下日誌檔案: {[str(p.name) for p in log_files]}")
    return log_files


def export_results(results: List[Dict[str, Any]], output_file: Path):
    """將分析結果匯出成 NDJSON 檔案 (一行一筆 JSON)。"""
    if not results:
        logger.info("本次執行沒有產生新的可匯出的結構化分析結果。")
        return

    logger.info(f"準備將 {len(results)} 筆結構化分析結果匯出至 {output_file}")
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "a", encoding="utf-8") as f_out:
            for rec in results:
                json_line = json.dumps(rec, ensure_ascii=False)
                f_out.write(json_line + "\n")
        logger.info(f"分析結果已成功匯出至 {output_file}")
    except PermissionError:
        logger.critical(
            f"無權限寫入分析結果檔案 {output_file}。"
            "請檢查權限或更改 LMS_ANALYSIS_OUTPUT_FILE 環境變數。"
        )
    except Exception as e:
        logger.error(f"匯出分析結果至 {output_file} 失敗: {e}", exc_info=True)


def main():
    """主執行函數"""
    logger.info("=" * 50)
    logger.info(f"進階日誌分析器啟動...")
    logger.info(f"目標日誌目錄: {settings.LMS_TARGET_LOG_DIR}")
    logger.info(f"分析結果匯出檔案: {settings.LMS_ANALYSIS_OUTPUT_FILE}")
    logger.info(f"運維日誌檔案: {settings.LMS_OPERATIONAL_LOG_FILE}")
    logger.info("=" * 50)

    # 檢查關鍵配置
    if not settings.OLLAMA_API_URL:
        logger.error("錯誤：環境變數 OLLAMA_API_URL 未設定。LLM 功能將停用。")

    # 尋找並處理日誌
    log_files_to_process = find_log_files(settings.LMS_TARGET_LOG_DIR)
    all_exported_data: List[Dict[str, Any]] = []

    if log_files_to_process:
        try:
            all_exported_data = process_and_analyze_logs(log_files_to_process)
        except Exception as main_e:
            logger.critical(f"主處理流程發生未預期錯誤: {main_e}", exc_info=True)
    else:
        logger.info("沒有日誌檔案需要處理，跳過主流程。")

    # 程式結束前儲存所有狀態並匯出結果
    try:
        logger.info("程式即將結束，正在儲存最終狀態...")
        save_log_state(STATE)
        VECTOR_DB.save()
        export_results(all_exported_data, settings.LMS_ANALYSIS_OUTPUT_FILE)
    except Exception as final_save_e:
        logger.error(f"結束前儲存狀態或匯出結果時發生錯誤: {final_save_e}", exc_info=True)
    finally:
        logger.info(f"最終 LLM 總使用統計: {COST_TRACKER.get_total_stats()}")
        logger.info("進階日誌分析器執行完畢。")


if __name__ == "__main__":
    main()
