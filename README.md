# Julia AI Image Studio

Streamlit 圖片轉影片工具。使用 Runway API 生成影片。

## 部署
1. 將 `app.py`、`requirements.txt`、`.gitignore` 和本檔上傳到 GitHub 儲存庫根目錄。
2. 在 Streamlit Community Cloud 建立 App，選擇此儲存庫，主程式為 `app.py`。
3. 在 App 的 **Settings → Secrets** 設定：

   ```toml
   RUNWAYML_API_SECRET = "你的 Runway API 金鑰"
   ```

**不要**把 API 金鑰放入 GitHub、對話或截圖。Runway API 可能按用量收費。

此版本依據對話中提供的 `app.py` 整理，尚未以真實 Runway 金鑰進行端到端測試。
