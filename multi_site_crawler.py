import os
import re
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import threading
import time
import schedule
import logging
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# === 抑制 SSL 警告 ===
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === 設定 ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === 建立帶重試的 Session ===
def create_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AntiFraudBot/3.0'})
    return session

session = create_session()

# === Selenium 設定（用於動態網站） ===
def get_selenium_driver():
    options = Options()
    options.add_argument('--headless')  # 無頭模式
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# === 初始化資料庫 ===
def init_db():
    conn = sqlite3.connect('anti_scam.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS scam_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            content TEXT UNIQUE,
            source TEXT,
            added_date TEXT
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("資料庫初始化完成")

# === 儲存資料 ===
def save_data(items, data_type, source):
    if not items:
        return 0
    conn = sqlite3.connect('anti_scam.db')
    c = conn.cursor()
    added = 0
    for item in items:
        try:
            c.execute("""
                INSERT OR IGNORE INTO scam_data (type, content, source, added_date)
                VALUES (?, ?, ?, ?)
            """, (data_type, str(item).strip(), source, datetime.now().isoformat()))
            if c.rowcount > 0:
                added += 1
        except Exception as e:
            logger.error(f"儲存錯誤 ({data_type}): {e}")
    conn.commit()
    conn.close()
    return added

# === 爬蟲函數（重試 + 備用 + Selenium）===
def crawl_165():
    urls, keywords = set(), set()
    added_urls, added_kw = 0, 0
    try:
        # 用 Selenium 處理動態頁面
        driver = get_selenium_driver()
        driver.get("https://165.npa.gov.tw/")
        time.sleep(5)  # 等待載入
        
        # 詐騙網站
        try:
            website_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="fraud/website"], a[href*="詐騙網站"]')
            for link in website_links:
                href = link.get_attribute('href')
                if href and '165' not in href and len(href) > 10:
                    urls.add(href.split('?')[0].split('#')[0])
        except:
            pass

        # 話術
        try:
            tactic_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="fraud/tactics"], a[href*="詐騙手法"]')
            for link in tactic_links:
                text = link.text.strip()[:100]
                if text and re.search(r'猜猜我是誰|帳戶|轉帳|緊急|投資', text):
                    keywords.add(text)
        except:
            pass
        
        driver.quit()
        
        added_urls = save_data(urls, 'url', '165.npa.gov.tw')
        added_kw = save_data(keywords, 'keyword', '165.npa.gov.tw')
        logger.info(f"165: +{added_urls} URL, +{added_kw} 話術")
    except Exception as e:
        logger.error(f"165 錯誤: {e}")
    
    return {
        'urls': list(urls),
        'keywords': list(keywords),
        'added': {'urls': added_urls, 'keywords': added_kw}
    }

def crawl_datagov():
    datasets = set()
    added = 0
    try:
        # 備用 API
        apis = [
            "https://data.gov.tw/api/v2/rest/dataset",
            "https://api.data.gov.tw/v2/rest/dataset"
        ]
        for api in apis:
            try:
                resp = session.get(api, params={'q': '詐騙', 'limit': 20}, timeout=15, verify=False)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get('result', {}).get('results', []) or data.get('data', [])
                    for item in results:
                        title = item.get('title', '') or item.get('dataset_title', '')
                        if '詐騙' in title:
                            datasets.add(title[:100])
                    break
            except:
                continue
        added = save_data(datasets, 'dataset', 'data.gov.tw')
        logger.info(f"data.gov.tw: +{added} 資料集")
    except Exception as e:
        logger.error(f"data.gov.tw 錯誤: {e}")
    
    return {
        'datasets': list(datasets),
        'added': added
    }

def crawl_tca():
    news = set()
    added = 0
    try:
        resp = session.get("https://www.tca.org.tw/news", timeout=20, verify=False)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            selectors = ['a[href*="/news/"]', '.news-title', '.title a', 'h3 a', '.article-title']
            for sel in selectors:
                items = soup.select(sel)
                for item in items:
                    title = item.get_text(strip=True)
                    if any(k in title for k in ['詐騙', '投資', '假', '消保', '警示']):
                        news.add(title[:100])
                if news:
                    break
            added = save_data(news, 'news', 'tca.org.tw')
            logger.info(f"TCA: +{added} 新聞")
    except Exception as e:
        logger.error(f"TCA 錯誤: {e}")
    
    return {
        'news': list(news),
        'added': added
    }

def crawl_alert():
    alerts = set()
    added = 0
    try:
        urls = [
            "https://www.npa.gov.tw/NPAB/content/Index/doc?cid=200&mid=200",
            "https://165.npa.gov.tw/fraud/alert"
        ]
        for url in urls:
            try:
                resp = session.get(url, timeout=20, verify=False)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    selectors = ['.news-title', '.list-title', '.item-title', 'h3', 'h4', '.alert-title']
                    for sel in selectors:
                        items = soup.select(sel)
                        for item in items:
                            title = item.get_text(strip=True)
                            if '詐騙' in title or '警示' in title:
                                alerts.add(title[:120])
                        if alerts:
                            break
                    break
            except:
                continue
        added = save_data(alerts, 'alert', 'npa.gov.tw')
        logger.info(f"警政署: +{added} 警示")
    except Exception as e:
        logger.error(f"警政署 錯誤: {e}")
    
    return {
        'alerts': list(alerts),
        'added': added
    }

# === 整合 + 背景排程 ===
def run_all_crawlers():
    logger.info("開始四站爬蟲...")
    result_165 = crawl_165()
    time.sleep(3)
    result_datagov = crawl_datagov()
    time.sleep(2)
    result_tca = crawl_tca()
    time.sleep(2)
    result_alert = crawl_alert()
    logger.info("爬蟲完成")
    
    total_added = (
        result_165['added'].get('urls', 0) + 
        result_165['added'].get('keywords', 0) +
        result_datagov['added'] +
        result_tca['added'] +
        result_alert['added']
    )
    
    logger.info(f"總新增: {total_added} 筆")
    return {
        '165': result_165,
        'datagov': result_datagov,
        'tca': result_tca,
        'alert': result_alert,
        'total_added': total_added
    }

def start_scheduler():
    schedule.every(6).hours.do(run_all_crawlers)
    run_all_crawlers()
    while True:
        schedule.run_pending()
        time.sleep(60)

# === 主程式 ===
if __name__ == "__main__":
    init_db()
    
    crawler_thread = threading.Thread(target=start_scheduler, daemon=True)
    crawler_thread.start()
    
    print("防詐爬蟲系統已啟動！")
    print("每 6 小時自動更新一次詐騙資料。")
    print("按 Ctrl+C 停止程式。")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n爬蟲系統已停止。")
