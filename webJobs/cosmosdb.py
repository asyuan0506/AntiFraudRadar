from dotenv import load_dotenv
import os
load_dotenv()

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

from jsonl_parser import JSONLParser
from embeddings_cohere import EmbeddingModel
from text_splitter import split_text_into_chunks
import uuid

class CosmosDBClient:
    def __init__(self):
        self.client = CosmosClient.from_connection_string(str(os.getenv("COSMOSDB_CONNECTION_STRING")))
        self.embedding_client = EmbeddingModel()
        self.databaseName = os.getenv("CONFIGURATION__AZURECOSMOSDB__DATABASENAME", "cosmicworks")
        self.database = self.client.get_database_client(self.databaseName)
        self.containerName = os.getenv("CONFIGURATION__AZURECOSMOSDB__CONTAINERNAME", "products")
        self.container = self.database.get_container_client(self.containerName)

    def get_latest_upserted_item_time(self):
        query_text = '''SELECT TOP 1 c.publication_date\
                        FROM c\
                        ORDER BY c.publication_date DESC'''
        items = list(self.container.query_items(
            query=query_text,
            enable_cross_partition_query=True
        ))

        import dateutil.parser 
        from datetime import timezone, timedelta
        latest_time = "1970-01-01T00:00:00Z"
        if len(items) > 0:
            latest_time = items[0].get("publication_date", "1970-01-01T00:00:00Z")
        return dateutil.parser.isoparse(latest_time).astimezone(timezone(timedelta(hours=8)))


    def upsert_news_item(self, jsonl_parser: JSONLParser, index: int) -> dict: 
        """
        Upsert a news item in the CosmosDB container from the parsed JSONL data[index].
        """
        item = {}
        item["news_id"] = jsonl_parser.get_article_object(index, "id")
        item["url"] = jsonl_parser.get_article_object(index, "url")
        item["source"] = jsonl_parser.get_article_object(index, "source")
        item["title"] = jsonl_parser.get_article_object(index, "title")
        item["publication_date"] = jsonl_parser.get_article_object(index, "publication_date")
        
        # Upsert items for each text chunk
        body_text = jsonl_parser.get_article_object(index, "body_text")
        if body_text != "":
            status_text = self.upsert_text_item(item, body_text)
        if status_text["status"] != "OK":
            return status_text

        # Upsert items for each image
        images = jsonl_parser.get_article_object(index, "images")
        if len(images) > 0:
            status_image = self.upsert_image_item(item, images)
            if status_image["status"] != "OK":
                return status_image
        return {"status": "OK"}
    
    def upsert_text_item(self, item: dict, body_text: str) -> dict: 
        item["type"] = "text_chunk"
        try:
            text_chunks = split_text_into_chunks(body_text, 
                                                 chunk_size=1000, 
                                                 chunk_overlap=200)
        except Exception as e:
            print(f"Error splitting text into chunks: {e}")
            return {"status": "Error", "stage": "Text Splitting"}
        
        try:
            embedded_chunks = self.embedding_client.get_text_embedding(text_chunks, "DOCUMENT")
        except Exception as e:
            print(f"Error in text splitting or embedding: {e}")
            return {"status": "Error", "stage": "Text Splitting or Embedding"}
        
        for i, chunk in enumerate(text_chunks):
            item["id"] = str(uuid.uuid4())
            item["content"] = chunk
            item["content_vector"] = embedded_chunks.data[i].embedding
            try:
                self.container.upsert_item(item)
            except Exception as e:
                print(f"Error creating item in CosmosDB: {e}")
                return {"status": "Error", "stage": "Text Upsert", "index": i}
    
        try:
            del item["type"]
            del item["id"]
            del item["content"]
            del item["content_vector"]
        except KeyError as e:
            print(f"KeyError during cleanup: {e}")
            return {"status": "Error", "stage": "Cleanup"}
            
        return {"status": "OK"}

    def upsert_image_item(self, item: dict, images: list) -> dict: 
        item["type"] = "image"
        for idx, image in enumerate(images):
            item["id"] = str(uuid.uuid4())
            item["image_url"] = image.get("original_url", "")
            item["caption"] = image.get("caption", "")
            item["alt_text"] = image.get("alt_text", "")
            image_path = image.get("storage_path", "")
            try:
                item["content_vector"] = self.embedding_client.get_image_embedding(
                                            image_path, "DOCUMENT").data[0].embedding
                self.container.upsert_item(item)
            except Exception as e:
                print(f"Error creating image item in CosmosDB: {e}")
                return {"status": "Error", "stage": "Image Upsert", "index": idx}
        
        return {"status": "OK"}
    
    def query_news_by_vector(self, vector, k=5):
        """
        Query news items similar to the given embedding vector.
        Args:
            vector: The embedding vector to query.
            k: Number of top similar items to retrieve.
            Returns:
            List of news items similar to the input vector.
        """
        query_text = f'''SELECT TOP {k} c.url, c.source, c.title, c.publication_date, c.content, c.image_url, c.caption, c.alt_text, VectorDistance(c.content_vector, {vector}) AS SimilarityScore\
                        FROM c\
                        ORDER BY VectorDistance(c.content_vector, {vector})'''
        results = self.container.query_items(
            query=query_text,
            enable_cross_partition_query=True,
            populate_query_metrics=True,
        )
        return list(results)
    
    def query_news_images_by_image_vector(self, image_vector, k=3):
        """
        Query news images similar to the given image vector.
        Args:
            image_vector: The embedding vector of the image to query.
            k: Number of top similar items to retrieve.
        Returns:
            List of news image items similar to the input image vector.
        """
        query_text = f'''SELECT TOP {k} c.news_id, c.image_url, c.caption, c.alt_text, VectorDistance(c.content_vector, {image_vector}) AS SimilarityScore\
                        FROM c\
                        WHERE c.type = "image"\
                        ORDER BY VectorDistance(c.content_vector, {image_vector})'''
        
        results = self.container.query_items(
            query=query_text,
            enable_cross_partition_query=True,
            populate_query_metrics=True,
        )
        return list(results)