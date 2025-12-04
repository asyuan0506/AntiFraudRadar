import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time
import logging
import urllib3
import uuid
import os
from urllib.parse import urljoin, urlparse
from PIL import Image
from io import BytesIO
import dateutil.parser

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
tz_taiwan = timezone(timedelta(hours=8))

OUTPUT_JSONL = 'scam_rag_dataset.jsonl'
LOCAL_IMAGE_DIR = 'images/news_images'

os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)


def get_latest_publication_date():
    """讀取 jsonl 最後一筆有 publication_date 的時間"""
    if not os.path.exists(OUTPUT_JSONL):
        return None
    
    latest_dt = None
    try:
        with open(OUTPUT_JSONL, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    pub_date = data.get("publication_date")
                    if not pub_date:
                        continue
                    dt = dateutil.parser.isoparse(pub_date)
                    if latest_dt is None or dt > latest_dt:
                        latest_dt = dt
                except:
                    continue
    except Exception as e:
        logger.warning(f"讀取最新時間失敗: {e}")
    
    return latest_dt.astimezone(tz_taiwan) if latest_dt else None

latest_pub_date = get_latest_publication_date()

if latest_pub_date:
    print(f"資料庫中最新的新聞發布時間：{latest_pub_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print("本次只會抓取「發布時間晚於此」的文章")
else:
    print("資料庫為空或無時間紀錄 → 首次執行，抓取全部文章")

web_information = {
    'www.cib.npa.gov.tw': {'text': 'ed_txt', 'image': ['ed_txt'], 'source': '刑事警察局預防科'},
    'news.tvbs.com.tw': {'text': 'article_content', 'image': ['article_content', 'img_box'], 'source': 'TVBS'},
    'udn.com': {'text': 'article-content__editor', 'image': ['article-content__cover', 'article-content__image'], 'source': '聯合新聞網'}
}

def get_storage_path(article_id):
    return f"./{LOCAL_IMAGE_DIR}/{article_id}_{uuid.uuid4().hex[:6]}.png"

def extract_pub_date(soup, domain):

    publish_meta = [
        'meta[property="article:published_time"]', 'meta[name="pubdate"]',
        'meta[property="og:published_time"]', 'meta[itemprop="datePublished"]'
    ]
    for sel in publish_meta:
        tag = soup.select_one(sel)
        if tag and tag.get('content'):
            try:
                dt = dateutil.parser.isoparse(tag['content'])
                if dt <= datetime.now(dt.tzinfo):
                    return dt.isoformat()
            except: continue

    if 'cib.npa.gov.tw' in domain:
        m = re.search(r'發布日期[:：\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', soup.get_text())
        if m:
            try:
                d = m.group(1).replace('年','-').replace('月','-').replace('日','')
                return datetime.strptime(d, '%Y-%m-%d').isoformat()
            except: pass

    elif 'tvbs.com.tw' in domain:
        tag = soup.select_one('.time') or soup.select_one('time')
        if tag and not any(x in tag.get_text() for x in ['小時前','分鐘前','剛剛']):
            try: return dateutil.parser.parse(tag.get_text(), fuzzy=True).isoformat()
            except: pass

    elif 'udn.com' in domain:
        tag = soup.select_one('.article-content__time')
        if tag and '更新' not in tag.get_text():
            try: return dateutil.parser.parse(tag.get_text(), fuzzy=True).isoformat()
            except: pass

    return None

def clean_body_text(soup_original, classes):
    try:
        soup = BeautifulSoup(str(soup_original), 'html.parser') 
    except Exception as e:
        print(f"Error creating soup copy: {e}")
        return ""

    container = soup.find('main') or soup.find('body')
    if not container: return ""
    tags = container.find(class_=classes) if isinstance(classes, str) else container
    if not tags: return ""
    
    for bad in tags.select('script, iframe, nav, header, footer, aside, div, span.endtext, strong'):
        bad.decompose()
        
    text = tags.get_text(separator='\n', strip=True)
    
    return '\n\n'.join(l.strip() for l in text.split('\n') if len(l.strip()) >= 5)


def extract_images(soup, base_url, article_id, classes):
    images = []
    container = soup.find('main') or soup.find('body')
    if not container: return images
    
    areas = []
    if isinstance(classes, list):
        for c in classes:
            a = container.find(class_=c)
            if a: areas.append(a)
    else:
        a = container.find(class_=classes)
        if a: areas.append(a)

    for area in areas:
        for tag in area(['iframe', 'a']):
            tag.decompose()
            
        for img in area.find_all('img'):
            src = img.get('data-original') or img.get('data-src') or img.get('src')
            if not src: continue
            
            url = urljoin(base_url, src)
            
            if any(i['original_url'] == url for i in images): continue
            
            try:
                r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, verify=False)
                
                if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''):
                    path = get_storage_path(article_id)
                    
                    from PIL import Image 
                    
                    Image.open(BytesIO(r.content)).save(path)
                    
                    images.append({
                        "original_url": url, 
                        "storage_path": path, 
                        "caption": img.get('alt', ''), 
                        "alt_text": img.get('alt', '')
                    })
            except Exception as e:
                continue
                
    return images

def extract_tags(text):
    tags = ['詐騙','投資','網拍','愛情','猜猜我是誰','檢警','求職','解除設定','ATM','人頭帳戶','虛擬貨幣','LINE','轉帳']
    return list(set(t for t in tags if t in text)) or ['詐騙']


def add_cib_path(chapters):
    chapters.extend([
        ("假網拍詐騙", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=7e614f6f-df9b-4ae2-8293-ed384fb1a470"),
        ("假投資", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a4f8d5ab-3d53-4d22-9411-031fddde7a4e"),
        ("ATM解除分期", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a61af506-a4ac-49eb-9c79-ef75ddc6f237"),
        ("假愛情交友", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=064fe6c9-ae2c-40d2-a7df-2e5a4223091f"),
        ("猜猜我是誰", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=4f04dab6-3ca5-4139-a94e-66be03b62ba3"),
        ("假冒公務員", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=b7cf505d-f709-4885-b06b-d29b092ce04f"),
        ("假求職", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=87a85079-c42f-48cb-9506-14e08c912a39"),
    ])

def add_tvbs_path(chapters, pages=15):
    base = 'https://news.tvbs.com.tw/news/searchresult/網路詐騙/news/'
    for i in range(1, pages+1):
        try:
            r = requests.get(f'{base}{i}', timeout=20, verify=False)
            time.sleep(0.5)
            soup = BeautifulSoup(r.text, 'html.parser')
            for li in soup.select('.news_list li a'):
                if li.get('href'):
                    chapters.append((li.get_text(strip=True), urljoin(base, li['href'])))
        except: continue

def add_udn_path(chapters, pages=15):
    for p in range(1, pages+1):
        try:
            r = requests.get("https://udn.com/api/more", params={
                "page": p, "id": "search:網路詐騙", "channelId": 2, "type": "searchword"
            }, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            r.raise_for_status()
            for item in r.json().get('lists', []):
                if item.get('titleLink') and item.get('title'):
                    chapters.append((item['title'], item['titleLink']))
        except: continue


def crawl_webs_to_jsonl(latest_pub_date=latest_pub_date):
    chapters = []
    add_cib_path(chapters)
    add_tvbs_path(chapters, pages=15)
    add_udn_path(chapters, pages=15)
    print(f"總共收集到 {len(chapters)} 個候選連結")

    new_count = skipped_old = 0
    mode = 'a' if os.path.exists(OUTPUT_JSONL) else 'w'

    with open(OUTPUT_JSONL, mode, encoding='utf-8') as f:
        for title_hint, url in chapters:

            try:
                r = requests.get(url, timeout=20, verify=False)
                time.sleep(1)
                if r.status_code != 200: continue

                soup = BeautifulSoup(r.text, 'html.parser')
                domain = urlparse(url).netloc
                if domain not in web_information: continue
                info = web_information[domain]

                pub_date_str = extract_pub_date(soup, domain)
                if not pub_date_str:
                    continue  

                pub_date = dateutil.parser.isoparse(pub_date_str).astimezone(tz_taiwan)

                if latest_pub_date and pub_date <= latest_pub_date:
                    skipped_old += 1
                    continue

                body = clean_body_text(soup, info['text'])
                if len(body) < 80: continue

                article_id = f"{domain.split('.')[0]}_{uuid.uuid4().hex[:8]}"
                article = {
                    "id": article_id,
                    "url": url,
                    "source": info['source'],
                    "title": soup.find('title').get_text(strip=True) if soup.find('title') else title_hint,
                    "publication_date": pub_date_str,
                    "crawl_timestamp": datetime.now(tz_taiwan).isoformat(timespec='seconds'),
                    "tags": extract_tags(body),
                    "body_text": body,
                    "images": extract_images(soup, url, article_id, info['image'])
                }

                f.write(json.dumps(article, ensure_ascii=False) + '\n')
                new_count += 1
                print(f"新增 → {article['title'][:60]} ({pub_date_str[:10]})")

            except Exception as e:
                logger.error(f"失敗 {url}: {e}")

    print(f"\n完成！本次新增 {new_count} 篇")
    return new_count


if __name__ == "__main__":
    print("啟動詐騙新聞增量爬蟲（以資料庫最新發布時間為準）\n")
    crawl_webs_to_jsonl()
    print("\n執行完畢！下次執行會自動接續最新時間")
