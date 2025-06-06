import hashlib
import logging
import os
from typing import List, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_MODEL: Optional[SentenceTransformer] = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    if SENTENCE_MODEL:
        # 動態更新 EMBED_DIM
        settings.EMBED_DIM = SENTENCE_MODEL.get_sentence_embedding_dimension() or 384
        logger.info(f"成功載入 SentenceTransformer 模型: {settings.EMBEDDING_MODEL_NAME} (維度: {settings.EMBED_DIM})")
except ImportError:
    logger.warning("[WARN] 未安裝 sentence-transformers，將使用 SHA256 偽向量。建議安裝: pip install sentence-transformers")
    SENTENCE_MODEL = None
except Exception as e:
    logger.error(f"載入 SentenceTransformer 模型失敗: {e}。將使用 SHA256 偽向量。")
    SENTENCE_MODEL = None


def embed(text: str) -> List[float]:
    """
    產生嵌入向量。
    優先使用 SentenceTransformer，若失敗則退回使用 SHA-256 偽向量。
    """
    if SENTENCE_MODEL:
        embedding_vector = SENTENCE_MODEL.encode(text, convert_to_numpy=True)
        return embedding_vector.tolist()

    logger.warning("正在使用 SHA-256 偽向量，這不適用於生產環境！")
    digest = hashlib.sha256(text.encode('utf-8', 'replace')).digest()
    vec_template = list(digest)
    vec = []
    while len(vec) < settings.EMBED_DIM:
        vec.extend(vec_template)
    return [v / 255.0 for v in vec[:settings.EMBED_DIM]]