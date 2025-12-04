import os, time
from cosmosdb import CosmosDBClient
from jsonl_parser import JSONLParser
import multi_site_crawler

def crawl_and_store_news():
    cosmosdb_client = CosmosDBClient()
    print("Crawling news websites...")
    latest_time = cosmosdb_client.get_latest_upserted_item_time()
    multi_site_crawler.crawl_webs_to_jsonl(latest_time)
    jsonl_parser = JSONLParser("scam_rag_dataset.jsonl")
    jsonl_parser.parse()

    num_items = jsonl_parser.get_articles_length()
    print(f"Crawled {num_items} news items. Storing to CosmosDB...")
    for index in range(num_items):
        if index % 3 == 0:
            print(f"upserted items: {index}, total: {num_items}, Sleeping for 60 second to avoid rate limit...")
            time.sleep(60)
        result = cosmosdb_client.upsert_news_item(jsonl_parser, index)
        if result["status"] != "OK":
            print(f"Error upserting news item at index {index}: {result}")
    print("Finished storing news items to CosmosDB.")
    print("Removing images folder...")
    os.system("rm -rf images/news_images/*")

if __name__ == "__main__":
    try:
        crawl_and_store_news()
    except Exception as e:
        print(f"Error occured: {e}")