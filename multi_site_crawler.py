import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import re
import json
from datetime import datetime
import schedule
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === 初始化資料庫 ===
def init_db():
    conn = sqlite3.connect('anti_scam.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS scam_data (
            id INTEGER PRIMARY KEY,
            type TEXT,        -- url / phone / keyword / news
            content TEXT UNIQUE,
            source TEXT,
            added_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

# === 通用儲存函數 ===
def save_data(items, data_type, source):
    conn = sqlite3.connect('anti_scam.db')
    c = conn.cursor()
    added = 0
    for item in items:
        try:
            c.execute("""
                INSERT OR IGNORE INTO scam_data (type, content, source, added_date)
                VALUES (?, ?, ?, ?)
            """, (data_type, item.strip(), source, datetime.now().isoformat()))
            added += 1
        except:
            continue
    conn.commit()
    conn.close()
    logger.info(f"[{source}] 新增 {added} 筆 {data_type}")

# === 1. 爬 165 反詐騙網站（詐騙網址 + 話術）===
def crawl_165():
    urls = set()
    keywords = set()
    
    try:
        # 1.1 詐騙網站頁面
        response = requests.get(
            "https://165.npa.gov.tw/#/fraud/website",
            headers={'User-Agent': 'AntiFraudBot/1.0 (+https://yourbot.com)'},
            timeout=15
        )
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取 script 中的 URL
        for script in soup.find_all('script'):
            if script.string and ('websiteList' in script.string or 'http' in script.string):
                found = re.findall(r'https?://[^\s"\'<>]+', script.string)
                for u in found:
                    if '165' not in u and len(u) > 10:
                        urls.add(u.split('?')[0].split('#')[0])
        
        # 1.2 話術解析頁面（範例）
        response2 = requests.get("https://165.npa.gov.tw/#/fraud/tactics", timeout=15)
        soup2 = BeautifulSoup(response2.text, 'html.parser')
        for div in soup2.find_all('div', class_='tactic-item'):
            text = div.get_text()
            if '猜猜我是誰' in text or '帳戶' in text or '轉帳' in text:
                keywords.add(text[:100])
        
        save_data(urls, 'url', '165.npa.gov.tw')
        save_data(keywords, 'keyword', '165.npa.gov.tw')
        
    except Exception as e:
        logger.error(f"165 爬蟲錯誤: {e}")

# === 2. 爬 data.gov.tw 開放資料（API 優先）===
def crawl_datagov():
    urls = set()
    try:
        # 搜尋 165 詐騙資料
        api_url = "https://ods.pmi.gov.tw/api/v1/datasets"
        params = {'q': '165', 'limit': 50}
        resp = requests.get(api_url, params=params, timeout=10)
        data = resp.json()
        
        for item in data.get('data', []):
            if '詐騙' in item['title']:
                # 假設有 CSV 下載連結
                if 'download' in item:
                    urls.add(item['download'])
        
        save_data(urls, 'dataset', 'data.gov.tw')
    except Exception as e:
        logger.error(f"data.gov.tw 錯誤: {e}")

# === 3. 爬 台灣打擊詐騙協會 (TCA) ===
def crawl_tca():
    news = set()
    try:
        response = requests.get(
            "https://www.tca.org.tw/news",
            headers={'User-Agent': 'AntiFraudBot/1.0'},
            timeout=15
        )
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for a in soup.select('a.title-link'):
            title = a.get_text(strip=True)
            if any(kw in title for kw in ['詐騙', '警示', '投資', '假']):
                news.add(title[:100])
        
        save_data(news, 'news', 'tca.org.tw')
    except Exception as e:
        logger.error(f"TCA 錯誤: {e}")

# === 4. 爬 警政署警示網 (alert.gov.tw) ===
def crawl_alert():
    alerts = set()
    try:
        response = requests.get(
            "https://www.alert.gov.tw/News",
            headers={'User-Agent': 'AntiFraudBot/1.0'},
            timeout=15
        )
        soup = BeautifulSoup(response.text, 'html.parser')
        
        for item in soup.select('.news-item'):
            title = item.get_text(strip=True)
            if '詐騙' in title or '警示' in title:
                alerts.add(title[:120])
        
        save_data(alerts, 'alert', 'alert.gov.tw')
    except Exception as e:
        logger.error(f"alert.gov.tw 錯誤: {e}")

# === 主爬蟲函數 ===
def run_all_crawlers():
    logger.info("開始執行四站爬蟲...")
    crawl_165()
    time.sleep(3)
    crawl_datagov()
    time.sleep(2)
    crawl_tca()
    time.sleep(2)
    crawl_alert()
    logger.info("四站爬蟲完成！")

# === 定時排程 ===
def start_scheduler():
    schedule.every(6).hours.do(run_all_crawlers)
    run_all_crawlers()  # 啟動時先跑一次
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# === Line Bot 查詢範例 ===
def check_scam_content(text):
    conn = sqlite3.connect('anti_scam.db')
    c = conn.cursor()
    
    # 查 URL
    urls = re.findall(r'https?://[^\s]+', text)
    for url in urls:
        c.execute("SELECT content FROM scam_data WHERE type='url' AND content LIKE ?", (f"%{url}%",))
        if c.fetchone():
            conn.close()
            return f"警告：偵測到詐騙網站：{url}"
    
    # 查關鍵字
    c.execute("SELECT content FROM scam_data WHERE type='keyword'")
    keywords = [row[0] for row in c.fetchall()]
    for kw in keywords:
        if kw in text:
            return f"警告：偵測到詐騙話術：{kw}"
    
    conn.close()
    return None

# === 啟動 ===
if __name__ == "__main__":
    init_db()
    # 單次執行
    # run_all_crawlers()
    
    # 或啟動排程
    start_scheduler()
