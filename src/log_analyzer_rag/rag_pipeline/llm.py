"""LLM analysis pipeline using a local Ollama/Llama3 server."""

import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from ..core.config import settings
from .cache import CACHE

logger = logging.getLogger(__name__)


class LLMCostTracker:
    def __init__(self):
        self.in_tokens_hourly = 0
        self.out_tokens_hourly = 0
        self.cost_hourly = 0.0
        self.total_in_tokens = 0
        self.total_out_tokens = 0
        self.total_cost = 0.0
        self._window_start_time = datetime.now(timezone.utc)

    def add_usage(self, in_tok: int, out_tok: int):
        self.in_tokens_hourly += in_tok
        self.out_tokens_hourly += out_tok
        current_cost = (
            in_tok / 1000 * settings.LMS_PRICE_IN_PER_1K_TOKENS
            + out_tok / 1000 * settings.LMS_PRICE_OUT_PER_1K_TOKENS
        )
        self.cost_hourly += current_cost
        self.total_in_tokens += in_tok
        self.total_out_tokens += out_tok
        self.total_cost += current_cost

    def reset_if_window_passed(self):
        if datetime.now(timezone.utc) - self._window_start_time > timedelta(hours=1):
            logger.info(
                "LLM 每小時費用窗口重置。上一小時: "
                f"Input Tokens: {self.in_tokens_hourly}, "
                f"Output Tokens: {self.out_tokens_hourly}, "
                f"Cost: ${self.cost_hourly:.4f}"
            )
            self.in_tokens_hourly = 0
            self.out_tokens_hourly = 0
            self.cost_hourly = 0.0
            self._window_start_time = datetime.now(timezone.utc)

    def get_hourly_cost(self) -> float:
        return self.cost_hourly

    def get_total_stats(self) -> dict:
        return {
            "total_input_tokens": self.total_in_tokens,
            "total_output_tokens": self.total_out_tokens,
            "total_cost_usd": self.total_cost,
        }


COST_TRACKER = LLMCostTracker()
LLM_ENABLED = bool(settings.OLLAMA_API_URL)
PROMPT_TEMPLATE_STR = """
System: 你是一位資安分析助手。請仔細評估以下 Web 伺服器日誌條目，判斷其是否顯示任何潛在的攻擊行為、可疑活動或明顯的錯誤。
你的分析應著重於識別模式，例如 SQL 注入、跨站腳本(XSS)、目錄遍歷、機器人掃描、暴力破解嘗試、異常的 User-Agent、非預期的 HTTP 狀態碼、過長的請求或回應時間等。

請根據你的分析，提供一個 JSON 格式的回應，包含以下欄位：
- "is_attack": boolean (如果日誌條目指示了攻擊或高度可疑行為，則為 true)
- "attack_type": string (如果 is_attack 為 true，請描述攻擊類型，例如 "SQL Injection", "XSS", "Path Traversal", "Bot Scanning", "Error Exploitation", "Unknown Anomaly"。如果 is_attack 為 false，則為 "N/A")
- "reason": string (簡要解釋你判斷的理由，即使 is_attack 為 false 也請說明為何正常或僅為低風險錯誤)
- "severity": string (攻擊的嚴重程度，例如 "High", "Medium", "Low"。如果 is_attack 為 false，則為 "None")

Log Entry:
{log_entry}

JSON Output:
"""


def _query_ollama_batch(prompts: List[str]) -> List[str]:
    """一次性向 Ollama 發送多個 prompt 並取得回應列表。"""
    payload = json.dumps({"model": settings.LLM_MODEL_NAME, "prompt": prompts, "stream": False}).encode("utf-8")
def llm_analyse(lines: List[str]) -> List[Optional[Dict[str, Any]]]:
    if not LLM_ENABLED:
        logger.warning("LLM 未啟用，跳過分析。")
        return [None] * len(lines)

    results: List[Optional[Dict[str, Any]]] = [None] * len(lines)
    original_indices_to_query: List[int] = []
    batch_prompts: List[str] = []

    for idx, line_content in enumerate(lines):
        cached_result = CACHE.get(line_content)
        if cached_result is not None:
            results[idx] = cached_result
        else:
            original_indices_to_query.append(idx)
            prompt = PROMPT_TEMPLATE_STR.replace("{log_entry}", line_content)
            batch_prompts.append(prompt)

    if not batch_prompts:
        logger.info("所有待分析日誌均命中快取。")
        return results

    COST_TRACKER.reset_if_window_passed()
    if COST_TRACKER.get_hourly_cost() >= settings.LMS_MAX_HOURLY_COST_USD:
        logger.warning(
            f"已達每小時 LLM 費用上限 (${settings.LMS_MAX_HOURLY_COST_USD:.2f})，本輪剩餘日誌將不進行分析。"
        )
        for i_orig in original_indices_to_query:
            results[i_orig] = {
                "is_attack": False,
                "attack_type": "N/A",
                "reason": "Budget limit reached, not analyzed.",
                "severity": "None",
            }
        return results

    logger.info(f"準備呼叫 LLM 分析 {len(batch_prompts)} 筆日誌。")

    total_in_tokens_batch = sum(len(p.split()) for p in batch_prompts)
    total_out_tokens_batch = 0
    try:
        responses = _query_ollama_batch(batch_prompts)
    except Exception as e:
        logger.error(f"批次呼叫 LLM 失敗: {e}")
        responses = [json.dumps({"is_attack": True, "attack_type": "LLM Error", "reason": str(e), "severity": "Medium"})] * len(batch_prompts)

    for i, response_text in enumerate(responses):
        try:
            analysis_result = json.loads(response_text)
        except Exception:
            analysis_result = {
                "is_attack": True,
                "attack_type": "LLM Error",
                "reason": "Invalid JSON",
                "severity": "Medium",
            }
        original_idx = original_indices_to_query[i]
        results[original_idx] = analysis_result
        CACHE.put(lines[original_idx], analysis_result)
        out_tok = len(response_text.split())
        total_out_tokens_batch += out_tok
    COST_TRACKER.add_usage(total_in_tokens_batch, total_out_tokens_batch)
    logger.info(
        f"LLM 呼叫完成。Input tokens (approx): {total_in_tokens_batch}, Output tokens (approx): {total_out_tokens_batch}"
    )

    if COST_TRACKER.get_hourly_cost() >= settings.LMS_MAX_HOURLY_COST_USD:
        logger.warning(
            f"LLM 處理後已達或超過每小時費用上限 (${settings.LMS_MAX_HOURLY_COST_USD:.2f})。"
        )
    return results
