"""Application configuration module.

此模組負責讀取及初始化專案所需的各項設定，
包含路徑位置、模型名稱以及成本控制參數等。
所有設定皆透過 ``pydantic-settings`` 讀取環境變數，
並提供 ``settings`` 物件供其他模組使用。
"""

import os
from pathlib import Path
from typing import Optional

# 使用 pydantic-settings 來處理環境變數，比手動 os.getenv 更強大、更安全
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    應用程式的組態設定。
    
    這個類別會自動從環境變數或專案根目錄下的 .env 檔案讀取設定。
    變數名稱需與此處定義的欄位名稱完全相同。
    """
    
    # --------------------------------------------------------------------------
    # 基礎路徑設定
    # --------------------------------------------------------------------------
    # 專案根目錄，預設為此檔案所在位置往上三層
    BASE_DIR: Path = Path(os.getenv("LMS_HOME", Path(__file__).resolve().parents[3]))
    # 存放狀態檔、向量索引等資料的目錄
    DATA_DIR: Path = BASE_DIR / "data"

    # --------------------------------------------------------------------------
    # 核心設定
    # --------------------------------------------------------------------------
    # Google Gemini API Key，這是執行 LLM 分析的必要條件
    GEMINI_API_KEY: Optional[str] = None

    # --------------------------------------------------------------------------
    # 檔案路徑設定
    # --------------------------------------------------------------------------
    # 要掃描的日誌檔案所在的目錄
    LMS_TARGET_LOG_DIR: Path = Path("/var/log/LMS_LOG")
    # 結構化分析結果的匯出檔案路徑
    LMS_ANALYSIS_OUTPUT_FILE: Path = Path("/var/log/analyzer_results.json")
    # 此腳本自身運維日誌的儲存檔案路徑
    LMS_OPERATIONAL_LOG_FILE: Path = BASE_DIR / "analyzer_script.log"
    # 存放日誌檔案讀取進度 (inode/offset) 的狀態檔路徑
    LOG_STATE_FILE: Path = DATA_DIR / "file_state.json"
    # FAISS 向量索引檔案的儲存路徑
    VECTOR_DB_PATH: Path = DATA_DIR / "faiss.index"

    # --------------------------------------------------------------------------
    # 模型與演算法設定
    # --------------------------------------------------------------------------
    # Sentence Transformer 的嵌入模型名稱
    EMBEDDING_MODEL_NAME: str = 'paraphrase-multilingual-MiniLM-L12-v2'
    # 要使用的 LLM 模型名稱
    LLM_MODEL_NAME: str = "gemini-1.5-flash-latest"
    # 嵌入向量的維度 (預設值，會被 embedding.py 中的模型實際維度動態覆蓋)
    EMBED_DIM: int = 384

    # --------------------------------------------------------------------------
    # 效能與成本控制
    # --------------------------------------------------------------------------
    # LLM 結果的 LRU 快取大小
    LMS_CACHE_SIZE: int = 10_000
    # 啟發式評分後，取分數最高的日誌百分比進行深度分析
    LMS_SAMPLE_TOP_PERCENT: int = 20
    # 批次呼叫 LLM 分析的日誌數量
    LMS_LLM_BATCH_SIZE: int = 10
    # 每小時 LLM API 的費用上限 (美元)
    LMS_MAX_HOURLY_COST_USD: float = 5.0
    # LLM 輸入 token 的價格 (每 1000 tokens)
    LMS_PRICE_IN_PER_1K_TOKENS: float = 0.000125
    # LLM 輸出 token 的價格 (每 1000 tokens)
    LMS_PRICE_OUT_PER_1K_TOKENS: float = 0.000375

    # --------------------------------------------------------------------------
    # FAISS 相似度閾值 (L2 距離)
    # --------------------------------------------------------------------------
    # 用於判斷與已知攻擊模式相似的 L2 距離閾值 (值越小越相似)
    SIM_T_ATTACK_L2_THRESHOLD: float = 0.3
    # 用於判斷與已知正常模式相似的 L2 距離閾值
    SIM_N_NORMAL_L2_THRESHOLD: float = 0.2

    # Pydantic-settings 的 model_config
    model_config = SettingsConfigDict(
        env_file=".env",              # 指定讀取 .env 檔案
        env_file_encoding="utf-8",    # .env 檔案編碼
        case_sensitive=True,          # 環境變數名稱大小寫敏感
        extra='ignore'                # 忽略 .env 中未在上面定義的多餘變數
    )

# 建立一個全域可用的 settings 實例
settings = Settings()

# --- 目錄初始化 ---
# 在程式啟動時，確保所有需要的資料目錄都存在
try:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # 檢查並建立非標準的父目錄
    if not settings.LMS_ANALYSIS_OUTPUT_FILE.parent.exists():
        settings.LMS_ANALYSIS_OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    if not settings.LMS_OPERATIONAL_LOG_FILE.parent.exists():
        settings.LMS_OPERATIONAL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
except Exception as e:
    # 在無法建立目錄時給出提示，通常是權限問題
    print(f"[CRITICAL] 無法建立必要的資料或日誌目錄，請檢查權限: {e}")
