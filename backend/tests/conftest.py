"""pytest 共用設定：測試一律不連線外部網站（openFDA、MedlinePlus、Gemini 向量另以假資料測試）"""
import os

os.environ["LIVE_SOURCES"] = "off"
os.environ["SEMANTIC_SEARCH"] = "off"   # 語意檢索另以假向量測試，見 test_retrieval.py
