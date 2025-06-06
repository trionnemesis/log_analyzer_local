"""Utilities for scoring log lines and updating the FAISS index."""

import logging
from typing import List, Tuple

from ..core.config import settings
from .scoring import fast_score
from ..rag_pipeline.embedding import embed
from ..rag_pipeline.vector_store import VECTOR_DB

logger = logging.getLogger(__name__)

def update_vector_index(new_log_lines: List[str]) -> List[Tuple[float, str]]:
    """
    對新增的日誌進行評分、抽樣、向量化並更新至 FAISS 索引。

    這個函式是 RAG 流程中 "Retrieval" 的基礎建設部分。

    Args:
        new_log_lines: 從日誌檔案中讀取到的新日誌行列表。

    Returns:
        一個元組列表，包含被選中進行深度分析的日誌及其啟發式分數。
        格式為 [(score, line_content), ...]。
        如果沒有日誌被選中，則回傳空列表。
    """
    if not new_log_lines:
        return []

    # 1. 快速評分
    logger.info(f"對 {len(new_log_lines)} 行新日誌進行啟發式評分...")
    scored_lines = sorted(
        [(fast_score(line), line) for line in new_log_lines],
        key=lambda x: x[0],
        reverse=True
    )

    # 2. 抽樣高分日誌
    # 取分數大於 0 的日誌，再取前 N%
    positive_scored_lines = [sl for sl in scored_lines if sl[0] > 0.0]
    if not positive_scored_lines:
        logger.info("所有新日誌的啟發式評分均為0，無需建立索引。")
        return []

    num_to_sample = max(1, int(len(positive_scored_lines) * settings.LMS_SAMPLE_TOP_PERCENT / 100))
    top_scored_lines_to_index = positive_scored_lines[:num_to_sample]

    top_lines_content = [line_content for _, line_content in top_scored_lines_to_index]
    logger.info(
        f"評分與抽樣完成，選出 {len(top_lines_content)} 行日誌進行向量化。"
        f"(最高分: {top_scored_lines_to_index[0][0]:.2f})"
    )

    # 3. 產生 Embedding 並更新向量索引
    if VECTOR_DB.index is not None:
        try:
            logger.info("正在產生文字嵌入向量...")
            line_embeddings = [embed(line) for line in top_lines_content]

            if line_embeddings:
                logger.info("正在將新向量新增至 FAISS 索引...")
                VECTOR_DB.add(line_embeddings)
                logger.info(f"成功將 {len(line_embeddings)} 個新向量存入 FAISS。")

        except Exception as e:
            logger.error(f"產生 embedding 或存入 FAISS 時發生錯誤: {e}", exc_info=True)
    else:
        logger.warning("FAISS 未啟用或索引未初始化，跳過 embedding 和向量索引更新。")

    # 4. 回傳被選中的高分日誌列表，供後續 LLM 分析使用
    return top_scored_lines_to_index
