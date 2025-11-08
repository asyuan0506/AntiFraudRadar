import dotenv, os
from azure.ai.inference import EmbeddingsClient
from azure.ai.inference.models import ImageEmbeddingInput, EmbeddingInputType
from azure.core.credentials import AzureKeyCredential
import numpy as np
from utils.image_utils import encode_image, decode_image

dotenv.load_dotenv()

class EmbeddingModel:
    endpoint = "https://testing1ai1foundry.services.ai.azure.com/models"
    deployment_name = "embed-v-4-0" # Support Language: en, fr, es, it, de, pt-br, ja, ko, zh-cn, ar
    api_key = os.getenv("COHERE_EMBEDDING_API_KEY")

    def __init__(self):
        self.client = EmbeddingsClient(
            endpoint=EmbeddingModel.endpoint,
            credential=AzureKeyCredential(str(EmbeddingModel.api_key)),
        )

    def get_text_embedding(self, texts, input_type="DOCUMENT"): 
        """
        Args:
            texts: List of strings.
            input_type: "TEXT", "QUERY", "DOCUMENT"
        Returns:
            response: Embedding response object.
        """
        response = self.client.embed(
            input=texts,
            input_type=EmbeddingInputType[input_type],
            model=self.deployment_name
        )
        return response

    def get_image_embedding(self, image_path, input_type="DOCUMENT"): 
        """
        Args:
            image_path: Path to the image file.
            input_type: "TEXT", "QUERY", "DOCUMENT"
        
        """
        data_url = encode_image(image_path)
        response = self.client.embed(
            input=[data_url],
            input_type=EmbeddingInputType[input_type],
            model=self.deployment_name
        )   
        return response

    def cosine_similarity(self, vector1, vector2):
        return np.dot(vector1, vector2) / (np.linalg.norm(vector1) * np.linalg.norm(vector2))

if __name__ == "__main__":
    print("Cohere Embedding Model Test")
    embedding_model = EmbeddingModel()

    # Test text embeddings
    texts = [
        "The quick brown fox jumps over the lazy dog.",
        "A fast dark-colored fox leaps above a sleepy canine.",
        "測試中文",
    ]
    response = embedding_model.get_text_embedding(texts)
    for item in response.data:
        length = len(item.embedding)
        print(
            f"data[{item.index}]: length={length}, [{item.embedding[0]}, {item.embedding[1]}, "
            f"..., {item.embedding[length-2]}, {item.embedding[length-1]}]"
        )
    query_texts = [
        "What animal is sleeping?",
    ]
    query_response = embedding_model.get_text_embedding(query_texts, input_type="QUERY")
    for item in response.data:
        length = len(item.embedding)
        print(
            f"data[{item.index}]: length={length}, [{item.embedding[0]}, {item.embedding[1]}, "
            f"..., {item.embedding[length-2]}, {item.embedding[length-1]}]"
        )
    # Calculate cosine similarity between the first query and all documents
    for query_item in query_response.data:
        for doc_item in response.data:
            similarity = embedding_model.cosine_similarity(query_item.embedding, doc_item.embedding)
            print(f"Cosine similarity between query[{query_item.index}] and doc[{doc_item.index}]: {similarity}")
   
    # Test image embeddings
    # response = embedding_model.get_image_embedding("images/fraud_message.png")
    # for item in response.data:
    #     length = len(item.embedding)
    #     print(
    #         f"data[{item.index}]: length={length}, [{item.embedding[0]}, {item.embedding[1]}, "
    #         f"..., {item.embedding[length-2]}, {item.embedding[length-1]}]"
    #     )

    # Test image encoding and decoding
    # encoded_image = encode_image("images/fraud_message.png")
    # decode_image(encoded_image, "images/decoded_fraud_message.png")
    