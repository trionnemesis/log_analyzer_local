import logging
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np
from ..core.config import settings

logger = logging.getLogger(__name__)

try:
    import faiss
except ImportError:
    logger.warning("[WARN] 未安裝 faiss-cpu，向量搜尋功能停用。請執行: pip install faiss-cpu")
    faiss = None

class VectorIndex:
    """封裝 FAISS Index 的簡易類別，包含自動載入 / 保存。"""
    def __init__(self, path: Path, dimension: int):
        self.path = path
        self.dimension = dimension
        self.index: Optional[faiss.Index] = None
        self._load()

    def _load(self):
        if faiss is None:
            return
        if self.path.exists():
            try:
                self.index = faiss.read_index(str(self.path))
                logger.info(f"從 {self.path} 載入 FAISS 索引，共 {self.index.ntotal if self.index else 0} 個向量。")
            except Exception as e:
                logger.error(f"讀取 FAISS 索引失敗: {e}。將建立新索引。")
                self.index = faiss.IndexFlatL2(self.dimension)
        else:
            logger.info(f"未找到 FAISS 索引檔，建立新的 L2 索引 (維度: {self.dimension})。")
            self.index = faiss.IndexFlatL2(self.dimension)

    def save(self):
        if faiss and self.index is not None:
            try:
                faiss.write_index(self.index, str(self.path))
                logger.info(f"FAISS 索引已儲存至 {self.path} ({self.index.ntotal} 個向量)。")
            except Exception as e:
                logger.error(f"儲存 FAISS 索引失敗: {e}")

    def search(self, vec: List[float], k: int = 5) -> Tuple[List[int], List[float]]:
        """回傳 (ids, dists)。若索引為空則回傳空列表。"""
        if faiss is None or self.index is None or self.index.ntotal == 0:
            return [], []
        query_vector = np.array([vec], dtype=np.float32)
        dists, ids = self.index.search(query_vector, k)
        return ids[0].tolist(), dists[0].tolist()

    def add(self, vecs: List[List[float]]):
        if faiss and self.index is not None:
            vectors_to_add = np.array(vecs, dtype=np.float32)
            self.index.add(vectors_to_add)
            logger.debug(f"新增 {len(vecs)} 個向量到 FAISS。目前總數: {self.index.ntotal}")

VECTOR_DB = VectorIndex(settings.VECTOR_DB_PATH, settings.EMBED_DIM)