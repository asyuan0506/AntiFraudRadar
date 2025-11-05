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
from PIL import Image
from io import BytesIO
import dateutil.parser  # 新增：pip install python-dateutil

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === 設定 ===
OUTPUT_JSONL = 'scam_rag_dataset.jsonl'
LOCAL_IMAGE_DIR = 'scam_images'
os.makedirs(LOCAL_IMAGE_DIR, exist_ok=True)

web_information = {
    'www.cib.npa.gov.tw': {'text': 'ed_txt', 'image': ['ed_txt'], 'source': '刑事警察局預防科'},
    'news.tvbs.com.tw': {'text': 'article_content', 'image': ['article_content', 'img_box'], 'source': 'TVBS'},
    'udn.com': {'text': 'article-content__editor', 'image': ['article-content__cover', 'article-content__image'], 'source': '聯合新聞網'}
}

# 模擬 storage_path
def get_storage_path(article_id):
    ext = '.png'
    filename = f"{article_id}_{uuid.uuid4().hex[:6]}{ext}"
    return f"./{LOCAL_IMAGE_DIR}/{filename}"

# === 新增：動態提取發布時間 ===
def extract_pub_date(soup, domain):
    """
    精準提取「發布時間」，避免抓到更新時間
    支援：刑事局、TVBS、聯合
    """
    # === 步驟 1：優先抓「發布時間」meta（絕不抓 modified）===
    publish_meta = [
        'meta[property="article:published_time"]',
        'meta[name="pubdate"]',
        'meta[property="og:published_time"]',
        'meta[name="publishdate"]',
        'meta[property="rnews:datePublished"]',
        'meta[itemprop="datePublished"]'
    ]
    for sel in publish_meta:
        tag = soup.select_one(sel)
        if tag and tag.get('content'):
            try:
                dt = dateutil.parser.isoparse(tag['content'])
                # 過濾未來時間（避免抓到「預約發布」）
                if dt > datetime.now(dt.tzinfo):
                    continue
                return dt.isoformat() + "Z"
            except:
                continue

    # === 步驟 2：<time> 標籤 + 關鍵字過濾 ===
    time_tag = soup.find('time')
    if time_tag:
        dt_str = time_tag.get('datetime') or time_tag.get_text(strip=True)
        if dt_str and ('發布' in dt_str or '刊登' in dt_str or '發佈' in dt_str):
            try:
                dt = dateutil.parser.parse(dt_str, fuzzy=True)
                if dt < datetime.now(dt.tzinfo):
                    return dt.isoformat() + "Z"
            except:
                pass

    # === 步驟 3：網站專屬精準選擇器 ===
    if 'cib.npa.gov.tw' in domain:
        # 刑事局：找「發布日期：2025年1月1日」
        text = soup.get_text()
        m = re.search(r'發布日期[:：\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', text)
        if m:
            try:
                date_str = m.group(1).replace('年', '-').replace('月', '-').replace('日', '')
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                return dt.isoformat() + "Z"
            except:
                pass

    elif 'tvbs.com.tw' in domain:
        # TVBS：找 .time 或 time 標籤，且包含「小時前」以外
        for sel in ['.time', 'time', '.date']:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(strip=True)
                if '小時前' in text or '分鐘前' in text or '剛剛' in text:
                    continue
                try:
                    dt = dateutil.parser.parse(text, fuzzy=True)
                    if dt.year >= 2000:
                        return dt.isoformat() + "Z"
                except:
                    continue

    elif 'udn.com' in domain:
        # 聯合：找 .article-content__time，且不是「更新」
        tag = soup.select_one('.article-content__time')
        if tag and '更新' not in tag.get_text():
            try:
                dt = dateutil.parser.parse(tag.get_text(strip=True), fuzzy=True)
                if dt.year >= 2000:
                    return dt.isoformat() + "Z"
            except:
                pass

    # === 步驟 4：備援 → 絕對不用 now()，改用「文章內文第一句時間」===
    first_para = soup.find('p')
    if first_para:
        text = first_para.get_text(strip=True)
        m = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', text)
        if m:
            try:
                date_str = m.group(1).replace('年', '-').replace('月', '-').replace('日', '')
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                return dt.isoformat() + "Z"
            except:
                pass

    # === 步驟 5：最後備援 → 真的找不到 → 留空或用爬蟲時間（建議留空）===
    return None  # 讓你知道「這篇沒抓到時間」

# === 清理純文字 ===
def clean_body_text(soup, classes):
    container = soup.find('main') or soup.find('body')
    if not container:
        return ""
    tags = container.find(class_=classes) if isinstance(classes, str) else container
    if not tags:
        return ""

    # 移除廣告、腳本
    for tag in tags.select('div, script, iframe, aside'):
        tag.decompose()

    text = tags.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) >= 5]
    return '\n\n'.join(lines)

# === 提取 + 下載圖片 ===
def extract_images(soup, base_url, article_id, classes):
    images = []
    container = soup.find('main') or soup.find('body')
    if not container:
        return images

    target_areas = []
    if isinstance(classes, list):
        for c in classes:
            area = container.find(class_=c)
            if area:
                target_areas.append(area)
    else:
        area = container.find(class_=classes)
        if area:
            target_areas.append(area)

    for area in target_areas:
        # 移除 iframe, a
        for tag in area.select('iframe, a'):
            tag.decompose()

        for img_tag in area.find_all('img'):
            src = img_tag.get('data-original') or img_tag.get('data-src') or img_tag.get('src')
            if not src:
                continue
            original_url = urljoin(base_url, src)
            if original_url in [img['original_url'] for img in images]:
                continue

            alt_text = img_tag.get('alt', '').strip()
            caption = ''
            parent = img_tag.find_parent(['figure', 'div'])
            if parent:
                figcaption = parent.find(['figcaption', 'span'])
                if figcaption:
                    caption = figcaption.get_text(strip=True)

            # 下載圖片
            storage_path = ""
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                img_resp = requests.get(original_url, headers=headers, timeout=15, verify=False)
                if img_resp.status_code == 200 and 'image' in img_resp.headers.get('Content-Type', ''):
                    storage_path = get_storage_path(article_id)
                    local_path = os.path.relpath(storage_path, '.')
                    img = Image.open(BytesIO(img_resp.content))
                    img.save(local_path)
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

# === 刑事局章節 ===
def add_cib_path(chapters):
    chapters.extend([
        ("假網拍詐騙", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=7e614f6f-df9b-4ae2-8293-ed384fb1a470"),
        ("假投資", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a4f8d5ab-3d53-4d22-9411-031fddde7a4e"),
        ("ATM解除分期", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=a61af506-a4ac-49eb-9c79-ef75ddc6f237"),
        ("假愛情交友", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=064fe6c9-ae2c-40d2-a7df-2e5a4223091f"),
        ("猜猜我是誰", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=4f04dab6-3ca5-4139-a94e-66be03b62ba3"),
        ("假冒公務員", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=b7cf505d-f709-4885-b06b-d29b092ce04f"),
        ("假求職", "https://www.cib.npa.gov.tw/ch/app/data/view?module=wg116&id=1909&serno=87a85079-c42f-48cb-9506-14e08c912a39"),
        ("二次詐騙", "https://www.cib.npa.gov.tw/ch/app/news/view?module=news&id=1887&serno=b434cf1c-d6fa-4e9c-9f55-6d8fe11e154d")
    ])

# === TVBS ===
def add_tvbs_path(chapter, pages=1):
    base_path = 'https://news.tvbs.com.tw/news/searchresult/網路詐騙/news/'
    for i in range(1, pages + 1):
        resp = requests.get(f'{base_path}{i}', timeout=20, verify=False)
        time.sleep(0.5)
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, 'html.parser')
        news_list = soup.find(class_='news_list')
        if not news_list:
            continue
        items = news_list.find_all('li')
        for item in items:
            a_tag = item.find('a')
            if a_tag and 'href' in a_tag.attrs:
                url = urljoin(base_path, a_tag['href'])
                title = a_tag.get_text(strip=True)
                chapter.append((title, url))

# === 聯合新聞網 ===
def add_udn_path(chapter, pages=2):
    base = "https://udn.com/api/more"
    params = {
        "page": 1,
        "id": "search:網路詐騙",
        "channelId": 2,
        "type": "searchword",
        "last_page": 27
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    }
    for i in range(1, pages + 1):
        params['page'] = i
        try:
            resp = requests.get(base, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            for news in data.get('lists', []):
                url = news.get('titleLink')
                title = news.get('title')
                if url and title:
                    chapter.append((title, url))
        except Exception as e:
            logger.warning(f"UDN 頁面 {i} 失敗: {e}")

# === 主爬蟲 ===
def crawl_webs_to_jsonl(f):
    chapters = []
    add_cib_path(chapters)
    add_tvbs_path(chapters, 2)
    add_udn_path(chapters, 2)
    print(f"總共取得 {len(chapters)} 個文章連結進行爬取")

    count = 0
    for chap_title, url in chapters:
        try:
            resp = requests.get(url, timeout=20, verify=False)
            time.sleep(0.5)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')

            domain = urlparse(url).netloc
            if domain not in web_information:
                continue
            info = web_information[domain]

            article_id = f"{domain.split('.')[0]}_{uuid.uuid4().hex[:8]}"
            title = soup.find('title').get_text(strip=True) if soup.find('title') else chap_title

            # 正確提取發布時間
            pub_date = extract_pub_date(soup, domain)

            body_text = clean_body_text(soup, info['text'])
            if len(body_text) < 50:
                continue

            images = extract_images(soup, url, article_id, info['image'])
            tags = extract_tags(body_text)

            article = {
                "iteration": count + 1,
                "id": article_id,
                "url": url,
                "source": info['source'],
                "title": title,
                "publication_date": pub_date,                    # 真實發布時間
                "crawl_timestamp": datetime.now().isoformat() + "Z",  # 爬蟲時間
                "tags": tags,
                "body_text": body_text,
                "images": images
            }
            f.write(json.dumps(article, ensure_ascii=False) + '\n')
            print(f"{count + 1}. {title[:50]}...（發布: {pub_date[:10]}，{len(images)} 圖）")
            count += 1
        except Exception as e:
            logger.error(f"錯誤 {url}: {e}")
    return count

# === 主執行 ===
def run_all_to_jsonl():
    with open(OUTPUT_JSONL, 'w', encoding='utf-8') as f:
        print("開始多來源爬蟲 → 輸出 RAG 標準 JSONL（含正確時間）")
        total = crawl_webs_to_jsonl(f)
        print(f"\n{'='*60}")
        print(f"完成！共生成 {total} 篇 JSONL 文章")
        print(f"publication_date = 文章真實發布時間")
        print(f"crawl_timestamp = 爬蟲執行時間")
        print(f"檔案: {OUTPUT_JSONL}")
        print(f"圖片儲存: {LOCAL_IMAGE_DIR}/")
        print(f"{'='*60}")

if __name__ == "__main__":
    run_all_to_jsonl()
    print("\nRAG 資料集已就緒！時間正確，可直接用於訓練與過濾")
