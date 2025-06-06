import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from ..core.config import settings
from .cache import CACHE

logger = logging.getLogger(__name__)

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.prompts import PromptTemplate
    from langchain_core.runnables import Runnable
except ImportError:
    logger.warning("[WARN] 未安裝 LangChain / Google GenAI，LLM 分析功能停用。")
    ChatGoogleGenerativeAI = None
    PromptTemplate = None
    Runnable = None


class LLMCostTracker:
    # ... (此處代碼與原腳本完全相同)
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
        current_cost = (in_tok / 1000 * settings.LMS_PRICE_IN_PER_1K_TOKENS) + \
                       (out_tok / 1000 * settings.LMS_PRICE_OUT_PER_1K_TOKENS)
        self.cost_hourly += current_cost
        self.total_in_tokens += in_tok
        self.total_out_tokens += out_tok
        self.total_cost += current_cost

    def reset_if_window_passed(self):
        if datetime.now(timezone.utc) - self._window_start_time > timedelta(hours=1):
            logger.info(
                f"LLM 每小時費用窗口重置。上一小時: "
                f"Input Tokens: {self.in_tokens_hourly}, Output Tokens: {self.out_tokens_hourly}, Cost: ${self.cost_hourly:.4f}"
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
            "total_cost_usd": self.total_cost
        }

COST_TRACKER = LLMCostTracker()
LLM_CHAIN: Optional[Runnable] = None
PROMPT: Optional[PromptTemplate] = None
GEMINI_ENABLED = bool(settings.GEMINI_API_KEY and ChatGoogleGenerativeAI)

if GEMINI_ENABLED:
    try:
        llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL_NAME,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.3,
            convert_system_message_to_human=True,
        )
        PROMPT_TEMPLATE_STR = """
System: 你是一位資安分析助手。請仔細評估以下 Web 伺服器日誌條目，判斷其是否顯示任何潛在的攻擊行為、可疑活動或明顯的錯誤。
你的分析應著重於識別模式，例如 SQL注入、跨站腳本(XSS)、目錄遍歷、機器人掃描、暴力破解嘗試、異常的 User-Agent、非預期的 HTTP 狀態碼、過長的請求或回應時間等。

請根據你的分析，提供一個 JSON 格式的回應，包含以下欄位：
- "is_attack": boolean (如果日誌條目指示了攻擊或高度可疑行為，則為 true)
- "attack_type": string (如果 is_attack 為 true，請描述攻擊類型，例如 "SQL Injection", "XSS", "Path Traversal", "Bot Scanning", "Error Exploitation", "Unknown Anomaly"。如果 is_attack 為 false，則為 "N/A")
- "reason": string (簡要解釋你判斷的理由，即使 is_attack 為 false 也請說明為何正常或僅為低風險錯誤)
- "severity": string (攻擊的嚴重程度，例如 "High", "Medium", "Low"。如果 is_attack 為 false，則為 "None")

Log Entry:
{log_entry}

JSON Output:
"""
        PROMPT = PromptTemplate(
            input_variables=["log_entry"],
            template=PROMPT_TEMPLATE_STR
        )
        LLM_CHAIN = PROMPT | llm
        logger.info(f"LLM ({settings.LLM_MODEL_NAME}) 初始化完成。")
    except Exception as e:
        logger.error(f"LLM 初始化失敗: {e}")
        GEMINI_ENABLED = False
else:
    if not settings.GEMINI_API_KEY:
        logger.warning("Gemini LLM 未啟用 (GEMINI_API_KEY 未設定)。")
    else:
        logger.warning("Gemini LLM 未啟用 (LangChain/Google GenAI 函式庫缺失)。")

def llm_analyse(lines: List[str]) -> List[Optional[Dict[str, Any]]]:
    # ... (此處代碼與原腳本完全相同，除了使用 settings 物件)
    if not LLM_CHAIN or not PROMPT:
        logger.warning("LLM 未啟用，跳過分析。")
        return [None] * len(lines)

    results: List[Optional[Dict[str, Any]]] = [None] * len(lines)
    original_indices_to_query: List[int] = []
    batch_inputs: List[Dict[str, str]] = []

    for idx, line_content in enumerate(lines):
        cached_result = CACHE.get(line_content)
        if cached_result is not None:
            results[idx] = cached_result
            logger.debug(f"快取命中: {line_content[:100]}...")
        else:
            original_indices_to_query.append(idx)
            batch_inputs.append({"log_entry": line_content})

    if not batch_inputs:
        logger.info("所有待分析日誌均命中快取。")
        return results

    COST_TRACKER.reset_if_window_passed()
    if COST_TRACKER.get_hourly_cost() >= settings.LMS_MAX_HOURLY_COST_USD:
        logger.warning(f"已達每小時 LLM 費用上限 (${settings.LMS_MAX_HOURLY_COST_USD:.2f})，本輪剩餘日誌將不進行分析。")
        for i_orig in original_indices_to_query:
             results[i_orig] = {"is_attack": False, "attack_type": "N/A", "reason": "Budget limit reached, not analyzed.", "severity": "None"}
        return results
    
    logger.info(f"準備批次呼叫 LLM 分析 {len(batch_inputs)} 筆日誌 (快取未命中部分)。")
    try:
        llm_responses = LLM_CHAIN.batch(batch_inputs, config={"max_concurrency": 5})
        total_in_tokens_batch = 0
        total_out_tokens_batch = 0

        for i, response in enumerate(llm_responses):
            original_idx = original_indices_to_query[i]
            log_line_for_cache = lines[original_idx]
            actual_content = getattr(response, 'content', getattr(response, 'text', str(response)))

            try:
                analysis_result = json.loads(actual_content)
                results[original_idx] = analysis_result
                CACHE.put(log_line_for_cache, analysis_result)
                
                # Token 估算
                prompt_str = PROMPT.format(log_entry=log_line_for_cache)
                in_tok_approx = len(prompt_str.split()) # 簡化估算
                out_tok_approx = len(actual_content.split()) # 簡化估算
                total_in_tokens_batch += in_tok_approx
                total_out_tokens_batch += out_tok_approx

            except json.JSONDecodeError as json_e:
                logger.error(f"LLM 回應 JSON 解析失敗 for log '{log_line_for_cache[:100]}...': {json_e}")
                logger.debug(f"原始 LLM 回應: {actual_content}")
                error_analysis = {"is_attack": True, "attack_type": "LLM Data Error", "reason": f"LLM response parsing error: {json_e}. Original: {str(actual_content)[:100]}...", "severity": "Medium"}
                results[original_idx] = error_analysis
                CACHE.put(log_line_for_cache, error_analysis)
            except Exception as e_inner:
                logger.error(f"處理 LLM 回應時發生未知錯誤 for log '{log_line_for_cache[:100]}...': {e_inner}")
                error_analysis = {"is_attack": True, "attack_type": "LLM Processing Error", "reason": f"LLM response processing error: {e_inner}", "severity": "Medium"}
                results[original_idx] = error_analysis
                CACHE.put(log_line_for_cache, error_analysis)
        
        COST_TRACKER.add_usage(total_in_tokens_batch, total_out_tokens_batch)
        logger.info(f"LLM 批次呼叫完成。Input tokens (approx): {total_in_tokens_batch}, Output tokens (approx): {total_out_tokens_batch}")

    except Exception as e_outer:
        logger.error(f"LLM 批次呼叫失敗: {e_outer}", exc_info=True)
        for i_orig in original_indices_to_query:
            if results[i_orig] is None:
                log_line_for_cache = lines[i_orig]
                error_analysis = {"is_attack": True, "attack_type": "LLM API Error", "reason": f"LLM batch API call failed: {e_outer}", "severity": "High"}
                results[i_orig] = error_analysis
                CACHE.put(log_line_for_cache, error_analysis)

    if COST_TRACKER.get_hourly_cost() >= settings.LMS_MAX_HOURLY_COST_USD:
        logger.warning(f"LLM 處理後已達或超過每小時費用上限 (${settings.LMS_MAX_HOURLY_COST_USD:.2f})。")
    return results