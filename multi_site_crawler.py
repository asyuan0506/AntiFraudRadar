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

main_types = {
    'www.cib.npa.gov.tw': {'text': 'ed_txt', 'image': ['ed_txt']},
    'news.tvbs.com.tw': {'text': 'article_content', 'image': ['article_content', 'img_box']}  # 文刪div，圖刪iframe...
}

# 模擬 storage_path（可換 S3 / Azure）
def get_storage_path(original_url, article_id):
    ext = os.path.splitext(urlparse(original_url).path)[1] or '.jpg'
    filename = f"{article_id}_{uuid.uuid4().hex[:6]}{ext}"
    return f"./{LOCAL_IMAGE_DIR}/{filename}"

# === 清理純文字（移除廣告、圖說、腳本）===
def clean_body_text(soup, types):
    soup = soup.find('main') if soup.find('main') else soup.find('body')
    tags = soup.find(class_=types)
    for tag in tags(['div']):
        tag.decompose()
    text = tags.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) >= 5]
    return '\n\n'.join(lines)

# === 提取 + 下載圖片 ===
def extract_images(soup, base_url, article_id, types):
    images = []
    soup = soup.find('main') if soup.find('main') else soup.find('body')
    for t in types:
        tags = soup.find(class_=t)
        for tag in tags(['iframe', 'a']):
            tag.decompose()
        for img_tag in tags.find_all('img'):
            src = img_tag.get('data-original') or img_tag.get('src')
            if not src:
                continue
            original_url = urljoin(base_url, src)
            
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

def add_tvbs_path(chapter, pages=1):
    base_path = 'https://news.tvbs.com.tw/news/searchresult/網路詐騙/news/'
    for i in range(1, pages + 1):
        resp = requests.get(f'{base_path}{i}', timeout=20, verify=False)
        time.sleep(0.5)
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, 'html.parser')
        news_list = soup.find(class_='news_list').find(class_='list').find_all('li')
        for news in news_list:
            a_tag = news.find('a')
            if a_tag and 'href' in a_tag.attrs:
                url = urljoin(base_path, a_tag['href'])
                title = a_tag.get_text(strip=True)
                chapter.append((title, url))

def add_cib_path(chapters):
    chapters.extend([
        ("假網拍詐騙", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=7e614f6f-df9b-4ae2-8293-ed384fb1a470"),
        ("假投資", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a4f8d5ab-3d53-4d22-9411-031fddde7a4e"),
        ("ATM解除分期", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a61af506-a4ac-49eb-9c79-ef75ddc6f237"),
        ("假愛情交友", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=064fe6c9-ae2c-40d2-a7df-2e5a4223091f"),
        ("猜猜我是誰", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=4f04dab6-3ca5-4139-a94e-66be03b62ba3"),
        ("假冒公務員", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=b7cf505d-f709-4885-b06b-d29b092ce04f"),
        ("假求職", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=87a85079-c42f-48cb-9506-14e08c912a39"),
        ("二次詐騙", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a2f50753-ab28-469a-a6ce-59368758d083")
    ])

def crawl_webs_to_jsonl(f):
    chapters = []
    add_cib_path(chapters)
    add_tvbs_path(chapters, 2)
    
    count = 0
    for chap_title, url in chapters:
        try:
            resp = requests.get(url, timeout=20, verify=False)
            time.sleep(0.5)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            domain = urlparse(url).netloc
            types = main_types[domain]
            article_id = f"cib_{uuid.uuid4().hex[:10]}"
            title = soup.find('title').get_text(strip=True) if soup.find('title') else chap_title
            body_text = clean_body_text(soup, types['text'])
            soup = BeautifulSoup(resp.text, 'html.parser')
            images = extract_images(soup, url, article_id, types['image'])
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

# === 主執行 ===
def run_all_to_jsonl():
    with open(OUTPUT_JSONL, 'w', encoding='utf-8') as f:
        print("開始多來源爬蟲 → 輸出 RAG 標準 JSONL")
        total = crawl_webs_to_jsonl(f)
        
        print(f"\n{'='*60}")
        print(f"完成！共生成 {total} 篇 JSONL 文章")
        print(f"檔案: {OUTPUT_JSONL}")
        print(f"圖片儲存: {LOCAL_IMAGE_DIR}/")
        print(f"結構：純文字 + images[] 分離 + storage_path")
        print(f"{'='*60}")

if __name__ == "__main__":
    run_all_to_jsonl()
    print("\nRAG 資料集已就緒！直接餵給 Embedding + Chunking 系統")
