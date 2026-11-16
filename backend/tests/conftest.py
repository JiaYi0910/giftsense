"""pytest 共用設定：測試一律不連線外部網站（openFDA、MedlinePlus、Gemini 另以假資料測試）"""
import os

os.environ["LIVE_SOURCES"] = "off"
os.environ["SEMANTIC_SEARCH"] = "off"   # 語意檢索另以假向量測試，見 test_retrieval.py
os.environ.pop("GEMINI_API_KEY", None)  # 問候語、快速提問不呼叫 Gemini（另以假資料測試，見 test_gemini.py）
