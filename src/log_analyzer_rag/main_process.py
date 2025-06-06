import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

from .core.config import settings
# 移除 fast_score, embed, VECTOR_DB 的導入，因為它們已被封裝到 indexer 中
from .data_processing.indexer import update_vector_index # <--- 新增導入
from .rag_pipeline.llm import llm_analyse, GEMINI_ENABLED
from .utils.file_tracker import tail_since

logger = logging.getLogger(__name__)


def process_and_analyze_logs(log_paths: List[Path]) -> List[Dict[str, Any]]:
    """
    主處理與分析流程的協調器。
    """
    # 1. 讀取增量日誌
    all_new_lines: List[str] = []
    for p in log_paths:
        all_new_lines.extend(tail_since(p))

    if not all_new_lines:
        logger.info("無新增日誌需要處理。")
        return []

    # 2. 對新日誌進行索引更新，並獲取需要深度分析的日誌列表 (***這是主要變更***)
    top_scored_lines_with_scores = update_vector_index(all_new_lines)

    if not top_scored_lines_with_scores:
        logger.info("經過濾與索引後，無日誌需要進一步的 LLM 分析。")
        return []

    top_lines_content = [line for _, line in top_scored_lines_with_scores]

    # 3. LLM 分析
    llm_analyses = llm_analyse(top_lines_content) if GEMINI_ENABLED else [None] * len(top_lines_content)

    # 4. 彙整結果 (此部分不變)
    exported_results: List[Dict[str, Any]] = []
    # ... (後續程式碼與前一版相同) ...
    # ...
    # ...
    alerts_found = 0
    logger.info("=" * 25 + " 分析結果彙總 " + "=" * 25)
    for i, analysis_result in enumerate(llm_analyses):
        original_line = top_lines_content[i]
        fast_s = top_scored_lines_with_scores[i][0]

        if not analysis_result: # 如果 LLM 未啟用或分析失敗
            analysis_result = {"is_attack": False, "attack_type": "N/A", "reason": "LLM disabled or failed, not analyzed.", "severity": "None"}

        exported_results.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original_log": original_line,
            "fast_score": float(f"{fast_s:.2f}"),
            "llm_analysis": analysis_result
        })

        is_attack = analysis_result.get("is_attack", False)
        if is_attack:
            alerts_found += 1
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        log_message = (
            f"日誌: {original_line}\n"
            f"  ├─ 啟發式評分: {fast_s:.2f}\n"
            f"  └─ LLM 分析: {json.dumps(analysis_result, ensure_ascii=False)}"
        )
        logger.log(log_level, log_message)

    logger.info("=" * (64))

    if alerts_found > 0:
        logger.warning(f"分析完成，共發現 {alerts_found} 個潛在攻擊警示。")
    else:
        logger.info("分析完成，未發現明確的攻擊警示。")

    return exported_results