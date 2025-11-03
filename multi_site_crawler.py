import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import logging
import urllib3
import uuid
import os
from urllib.parse import urljoin, urlparse
import feedparser  

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === 設定 ===
OUTPUT_JSONL = 'scam_rag_dataset.jsonl'
LOCAL_IMAGE_DIR = 'scam_images'
os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)

# 模擬 storage_path（可換 S3 / Azure）
def get_storage_path(original_url, article_id):
    ext = os.path.splitext(urlparse(original_url).path)[1] or '.jpg'
    filename = f"{article_id}_{uuid.uuid4().hex[:6]}{ext}"
    return f"./{LOCAL_IMAGE_DIR}/{filename}"

# === 清理純文字（移除廣告、圖說、腳本）===
def clean_body_text(soup):
    for tag in soup(['script', 'style', 'nav', 'footer', 'aside', 'figcaption', 'advertisement']):
        tag.decompose()
    text = soup.get_text(separator='\n', strip=True)
    lines = [line for line in text.split('\n') if line.strip() and len(line) > 10]
    return '\n\n'.join(lines)

# === 提取 + 下載圖片 ===
def extract_images(soup, base_url, article_id):
    images = []
    seen_urls = set()
    for img_tag in soup.find_all('img'):
        src = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-original')
        if not src or src in seen_urls:
            continue
        original_url = urljoin(base_url, src)
        seen_urls.add(original_url)
        
        alt_text = img_tag.get('alt', '').strip()
        caption = ''
        parent = img_tag.find_parent(['figure', 'div'])
        if parent:
            figcaption = parent.find('figcaption')
            if figcaption:
                caption = figcaption.get_text(strip=True)
        
        # 下載圖片
        storage_path = ""
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            img_resp = requests.get(original_url, headers=headers, timeout=15, verify=False)
            if img_resp.status_code == 200 and img_resp.headers.get('Content-Type', '').startswith('image/'):
                storage_path = get_storage_path(original_url, article_id)
                local_path = os.path.relpath(storage_path, '.')
                with open(local_path, 'wb') as f:
                    f.write(img_resp.content)
                logger.info(f"下載圖片: {local_path}")
        except Exception as e:
            logger.warning(f"圖片下載失敗 {original_url}: {e}")
            continue
        
        images.append({
            "original_url": original_url,
            "storage_path": storage_path,
            "caption": caption or alt_text,
            "alt_text": alt_text
        })
    return images

# === 提取話術標籤 ===
def extract_tags(text):
    tag_patterns = ['詐騙', '投資', '網拍', '愛情', '猜猜我是誰', '檢警', '求職', '解除設定']
    tags = [t for t in tag_patterns if t in text]
    return list(set(tags)) or ["詐騙", "話術"]

# === 刑事局 8 章 ===
def crawl_cib_to_jsonl(f):
    chapters = [
        ("假網拍詐騙", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=7e614f6f-df9b-4ae2-8293-ed384fb1a470"),
        ("假投資", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a4f8d5ab-3d53-4d22-9411-031fddde7a4e"),
        ("ATM解除分期", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a61af506-a4ac-49eb-9c79-ef75ddc6f237"),
        ("假愛情交友", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=064fe6c9-ae2c-40d2-a7df-2e5a4223091f"),
        ("猜猜我是誰", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=4f04dab6-3ca5-4139-a94e-66be03b62ba3"),
        ("假冒公務員", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=b7cf505d-f709-4885-b06b-d29b092ce04f"),
        ("假求職", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=87a85079-c42f-48cb-9506-14e08c912a39"),
        ("二次詐騙", "https://www.cib.npa.gov.tw/ch/app/news/view?module=news&id=1887&serno=b434cf1c-d6fa-4e9c-9f55-6d8fe11e154d")
    ]
    
    count = 0
    for chap_title, url in chapters:
        try:
            resp = requests.get(url, timeout=20, verify=False)
            time.sleep(2)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            article_id = f"cib_{uuid.uuid4().hex[:10]}"
            title = soup.find('title').get_text(strip=True) if soup.find('title') else chap_title
            body_text = clean_body_text(soup)
            images = extract_images(soup, url, article_id)
            tags = extract_tags(body_text)
            
            article = {
                "id": article_id,
                "url": url,
                "source": "刑事警察局",
                "title": title,
                "publication_date": datetime.now().isoformat() + "Z",
                "crawl_timestamp": datetime.now().isoformat() + "Z",
                "authors": ["刑事警察局預防科"],
                "tags": tags,
                "body_text": body_text,
                "images": images
            }
            f.write(json.dumps(article, ensure_ascii=False) + '\n')
            print(f"刑事局 ✓ {title}（{len(images)} 圖）")
            count += 1
        except Exception as e:
            logger.error(f"刑事局錯誤 {url}: {e}")
    return count

# === PTT 詐騙板 ===
def crawl_ptt_to_jsonl(f):
    count = 0
    try:
        url = "https://www.ptt.cc/bbs/Bunco/search?q=詐騙"
        headers = {'Cookie': 'over18=1'}
        resp = requests.get(url, headers=headers, timeout=20, verify=False)
        time.sleep(2)
        if resp.status_code != 200:
            return 0
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('.title a')[:5]
        
        for a in links:
            title = a.get_text(strip=True)
            post_url = 'https://www.ptt.cc' + a['href']
            try:
                post_resp = requests.get(post_url, headers=headers, timeout=20, verify=False)
                time.sleep(3)
                if post_resp.status_code == 200:
                    post_soup = BeautifulSoup(post_resp.text, 'html.parser')
                    content_div = post_soup.select_one('#main-content')
                    raw_text = content_div.get_text(strip=True, separator='\n') if content_div else ""
                    body_text = clean_body_text(post_soup)
                    article_id = f"ptt_{uuid.uuid4().hex[:10]}"
                    images = extract_images(post_soup, post_url, article_id)
                    tags = extract_tags(body_text)
                    
                    article = {
                        "id": article_id,
                        "url": post_url,
                        "source": "PTT-Bunco",
                        "title": title,
                        "publication_date": datetime.now().isoformat() + "Z",
                        "crawl_timestamp": datetime.now().isoformat() + "Z",
                        "authors": ["PTT 網友"],
                        "tags": tags,
                        "body_text": body_text,
                        "images": images
                    }
                    f.write(json.dumps(article, ensure_ascii=False) + '\n')
                    print(f"PTT ✓ {title}（{len(images)} 圖）")
                    count += 1
            except: continue
    except Exception as e:
        logger.error(f"PTT 錯誤: {e}")
    return count

# === Google 新聞 ===
def crawl_google_to_jsonl(f):
    count = 0
    try:
        rss_url = "https://news.google.com/rss/search?q=台灣+詐騙+話術&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:8]:
            title = entry.title
            link = entry.link
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(link, headers=headers, timeout=20, verify=False)
                time.sleep(4)
                if resp.status_code == 200 and 'paywall' not in resp.text.lower():
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    content_tag = soup.find('article') or soup.find('div', class_=re.compile('content|article|story'))
                    raw_text = content_tag.get_text() if content_tag else entry.get('summary', '')
                    body_text = clean_body_text(soup)
                    if len(body_text) < 100:
                        continue
                    article_id = f"google_{uuid.uuid4().hex[:10]}"
                    images = extract_images(soup, link, article_id)
                    tags = extract_tags(body_text)
                    
                    article = {
                        "id": article_id,
                        "url": link,
                        "source": "Google News",
                        "title": title,
                        "publication_date": entry.get('published', datetime.now().isoformat() + "Z"),
                        "crawl_timestamp": datetime.now().isoformat() + "Z",
                        "authors": ["新聞媒體"],
                        "tags": tags,
                        "body_text": body_text,
                        "images": images
                    }
                    f.write(json.dumps(article, ensure_ascii=False) + '\n')
                    print(f"Google ✓ {title[:50]}...（{len(images)} 圖）")
                    count += 1
            except: continue
    except Exception as e:
        logger.error(f"Google 錯誤: {e}")
    return count

# === 主執行 ===
def run_all_to_jsonl():
    with open(OUTPUT_JSONL, 'w', encoding='utf-8') as f:
        total = 0
        print("開始多來源爬蟲 → 輸出 RAG 標準 JSONL")
        total += crawl_cib_to_jsonl(f)
        total += crawl_ptt_to_jsonl(f)
        total += crawl_google_to_jsonl(f)
        
        print(f"\n{'='*60}")
        print(f"完成！共生成 {total} 篇 JSONL 文章")
        print(f"檔案: {OUTPUT_JSONL}")
        print(f"圖片儲存: {LOCAL_IMAGE_DIR}/")
        print(f"結構：純文字 + images[] 分離 + storage_path")
        print(f"{'='*60}")

if __name__ == "__main__":
    run_all_to_jsonl()
    print("\nRAG 資料集已就緒！直接餵給 Embedding + Chunking 系統")
