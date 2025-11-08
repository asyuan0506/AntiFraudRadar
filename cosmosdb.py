from dotenv import load_dotenv
import os
load_dotenv()

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

import uuid
import json

class CosmosDBClient:
    def __init__(self):
        self.client = CosmosClient.from_connection_string(str(os.getenv("COSMOSDB_CONNECTION_STRING")))
        self.databaseName = os.getenv("CONFIGURATION__AZURECOSMOSDB__DATABASENAME", "cosmicworks")
        self.database = self.client.get_database_client(self.databaseName)
        self.containerName = os.getenv("CONFIGURATION__AZURECOSMOSDB__CONTAINERNAME", "products")
        self.container = self.database.get_container_client(self.containerName)

    def upsert_news_item(self, item: dict): #TODO: Dedicate Function for News Item
        return self.container.upsert_item(item)
    
    def query_news_by_vector(self, vector):
        query_text = f'''SELECT TOP 5 c.url, c.source, c.title, c.publication_date, c.tags, c.body_text, VectorDistance(c.content_vector, {vector}) AS SimilarityScore\
                        FROM c\
                        ORDER BY VectorDistance(c.content_vector, {vector})'''
        results = self.container.query_items(
            query=query_text,
            enable_cross_partition_query=True,
            populate_query_metrics=True,
        )
        return [item for item in results]
    
    # def query_news_by_vector_and_text(self, vector, text): # Only Available for English
    #     query_text = f'''SELECT TOP 5 c.url, c.source, c.title, c.publication_date, c.tags, c.body_text, VectorDistance(c.content_vector, {vector}) AS SimilarityScore\
    #                     FROM c\
    #                     ORDER BY RANK RRF(FullTextScore(c.body_text, "{text}"), VectorDistance(c.content_vector, {vector}))'''
    #     results = self.container.query_items(
    #         query=query_text,
    #         enable_cross_partition_query=True,
    #         populate_query_metrics=True,
    #     )
    #     return results

new_item = {
        "id": "aaaaaaaa-0000-1111-2222-bbbbbbbbbbbb",
        "news_id": "gear-surf-surfboards",
        "name": "Yamba Surfboard",
        "quantity": 12,
        "sale": False,
    }



if __name__ == "__main__":
    import embeddings_cohere
    print("CosmosDB Client Test")
    cosmosdb_client = CosmosDBClient()
    print("Initialized CosmosDB Client")
    print("Initializing Cohere Embedding Client...")
    embedding_client = embeddings_cohere.EmbeddingModel()
    print("Cohere Embedding Client Initialized")
    embedding = embedding_client.get_text_embedding(["遊戲點數"], input_type="QUERY")
    created_item = cosmosdb_client.upsert_news_item(new_item)
    print(f"Upserted item:\t{created_item}")

    items = cosmosdb_client.query_news_by_vector(embedding.data[0].embedding)
    output = json.dumps(items, indent=True)
    print(f"Query Results:\n{output}")