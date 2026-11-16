"""pytest 共用設定：測試一律不連線外部網站（openFDA、MedlinePlus 的即時查詢另以假資料測試，見 test_live_sources.py）"""
import os

os.environ["LIVE_SOURCES"] = "off"
