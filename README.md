# 進階日誌分析器 (RAG 版本)

這是一個使用檢索增強生成 (RAG) 技術，結合大型語言模型 (LLM) 來自動分析 Web 伺服器日誌的專案。

## 功能

- **增量讀取**: 只處理上次執行後新增的日誌內容。
- **快速篩選**: 使用啟發式規則快速評分，篩選出可疑日誌。
- **向量檢索**: 將可疑日誌轉換為向量並存入 FAISS，用於尋找相似的攻擊模式。
- **LLM 深度分析**: 將高風險日誌發送給本機的 Llama3（透過 Ollama）進行深度分析，判斷攻擊類型和嚴重性。
- **成本控制**: 內建快取、批次處理和每小時費用上限，防止意外的高昂費用。
- **結構化輸出**: 將分析結果匯出為 JSON 格式，方便後續處理。

## 安裝

1.  安裝 [Poetry](https://python-poetry.org/docs/#installation)。
2.  安裝專案依賴:
    ```bash
    poetry install
    ```

## 設定

1.  複製環境變數模板檔案:
    ```bash
    cp .env.example .env
    ```
2.  編輯 `.env` 檔案，視需要設定 `OLLAMA_API_URL`（預設為 `http://localhost:11434/api/generate`）。
3.  根據需求修改其他路徑或參數設定。

## 如何執行

直接執行 `run.py` 腳本:

```bash
poetry run python run.py
```
