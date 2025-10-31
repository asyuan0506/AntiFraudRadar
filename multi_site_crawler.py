# app.py
import os
import re
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexMessage, FlexContainer
import threading
import time
import schedule
import logging

# === 設定 ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Line Bot 設定（請替換）
CHANNEL_ACCESS_TOKEN = "YOUR_CHANNEL_ACCESS_TOKEN"
CHANNEL_SECRET = "YOUR_CHANNEL_SECRET"
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

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
            logger.error(f"儲存錯誤: {e}")
    conn.commit()
    conn.close()
    return added

# === 爬蟲函數 ===
def crawl_165():
    urls, keywords = set(), set()
    headers = {'User-Agent': 'AntiFraudBot/1.0'}
    try:
        # 詐騙網站
        resp = requests.get("https://165.npa.gov.tw/#/fraud/website", headers=headers, timeout=15)
        matches = re.findall(r'https?://[^\s"\'<>]+', resp.text)
        for u in matches:
            if '165' not in u and len(u) > 10:
                urls.add(u.split('?')[0].split('#')[0])
        
        # 話術
        resp2 = requests.get("https://165.npa.gov.tw/#/fraud/tactics", headers=headers, timeout=15)
        soup = BeautifulSoup(resp2.text, 'html.parser')
        for div in soup.find_all('div', string=re.compile('猜猜我是誰|帳戶|轉帳|緊急')):
            text = div.get_text(strip=True)[:100]
            if text:
                keywords.add(text)
        
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
    try:
        api = "https://ods.pmi.gov.tw/api/v1/datasets"
        resp = requests.get(api, params={'q': '165', 'limit': 20}, timeout=10)
        for item in resp.json().get('data', []):
            if '詐騙' in item.get('title', ''):
                datasets.add(item.get('title', '')[:100])
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
    try:
        resp = requests.get("https://www.tca.org.tw/news", headers={'User-Agent': 'AntiFraudBot'}, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.select('a[href*="/news/"]'):
            title = a.get_text(strip=True)
            if any(k in title for k in ['詐騙', '投資', '假']):
                news.add(title[:100])
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
    try:
        resp = requests.get("https://www.alert.gov.tw/News", headers={'User-Agent': 'AntiFraudBot'}, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for item in soup.select('.card-title, .news-title'):
            title = item.get_text(strip=True)
            if '詐騙' in title or '警示' in title:
                alerts.add(title[:120])
        added = save_data(alerts, 'alert', 'alert.gov.tw')
        logger.info(f"alert.gov.tw: +{added} 警示")
    except Exception as e:
        logger.error(f"alert.gov.tw 錯誤: {e}")
    
    return {
        'alerts': list(alerts),
        'added': added
    }

# === 整合函式：一次回傳全部資料 ===
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
    
    return {
        '165': result_165,
        'datagov': result_datagov,
        'tca': result_tca,
        'alert': result_alert,
        'total_added': (
            result_165['added'].get('urls', 0) + 
            result_165['added'].get('keywords', 0) +
            result_datagov['added'] +
            result_tca['added'] +
            result_alert['added']
        )
    }
# === 背景排程 ===
def start_scheduler():
    schedule.every(6).hours.do(run_all_crawlers)
    run_all_crawlers()  # 啟動先跑一次
    while True:
        schedule.run_pending()
        time.sleep(60)

# === 查詢詐騙 ===
def check_scam(text):
    conn = sqlite3.connect('anti_scam.db')
    c = conn.cursor()
    
    # 查 URL
    urls = re.findall(r'https?://[^\s]+', text)
    for url in urls:
        url_clean = url.split('?')[0].split('#')[0]
        c.execute("SELECT content FROM scam_data WHERE type='url' AND content LIKE ?", (f"%{url_clean}%",))
        if c.fetchone():
            conn.close()
            return f"危險！偵測到詐騙網站：\n{url_clean}\n\n請勿點擊或輸入個資！"
    
    # 查關鍵字
    c.execute("SELECT content FROM scam_data WHERE type='keyword'")
    for (kw,) in c.fetchall():
        if kw in text:
            return f"警告！偵測到詐騙話術：\n「{kw}」\n\n請提高警覺！"
    
    conn.close()
    return None

# === Line Bot 處理 ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    reply = check_scam(user_text)
    
    if reply:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
    else:
        # 可加入其他回應
        pass

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# === 啟動 ===
if __name__ == "__main__":
    init_db()
    
    # 啟動背景爬蟲
    crawler_thread = threading.Thread(target=start_scheduler, daemon=True)
    crawler_thread.start()
    
    # 啟動 Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
