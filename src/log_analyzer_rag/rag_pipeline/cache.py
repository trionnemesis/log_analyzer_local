import logging
from collections import OrderedDict
from typing import Any, Optional
from ..core.config import settings

logger = logging.getLogger(__name__)

class LRUCache(OrderedDict):
    """簡單的 LRU 快取實現"""
    def __init__(self, capacity: int):
        super().__init__()
        self.capacity = capacity
        logger.info(f"LRU 快取已初始化，容量為 {capacity}。")

    def get(self, key: Any) -> Optional[Any]:
        if key in self:
            self.move_to_end(key)
            return self[key]
        return None

    def put(self, key: Any, value: Any):
        if key in self:
            self.move_to_end(key)
        self[key] = value
        if len(self) > self.capacity:
            self.popitem(last=False)

CACHE = LRUCache(settings.LMS_CACHE_SIZE)