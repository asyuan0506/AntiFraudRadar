import dotenv, os
from azure.ai.inference import EmbeddingsClient
from azure.ai.inference.models import ImageEmbeddingInput, EmbeddingInputType
from azure.core.credentials import AzureKeyCredential
import numpy as np
from image_utils import encode_image, decode_image
import time, random # For exponential backoff

dotenv.load_dotenv()

class EmbeddingModel:
    endpoint = "https://ntpufsl-antifraudradartest.services.ai.azure.com/models"
    deployment_name = "embed-v-4-0" # Support Language: en, fr, es, it, de, pt-br, ja, ko, zh-cn, ar
    api_key = os.getenv("COHERE_EMBEDDING_API_KEY")

    def __init__(self):
        self.client = EmbeddingsClient(
            endpoint=EmbeddingModel.endpoint,
            credential=AzureKeyCredential(str(EmbeddingModel.api_key)),
        )
        self.max_retries = 6 # TODO: Fix experience rate limit problem

    def get_text_embedding(self, texts:list[str], input_type="DOCUMENT"): 
        """
        Args:
            texts: List of strings.
            input_type: "TEXT", "QUERY", "DOCUMENT"
        Returns:
            response: Embedding response object.
        """
        for attempt in range(self.max_retries):
            try:
                response = self.client.embed(
                    input=texts,
                    input_type=EmbeddingInputType[input_type],
                    model=self.deployment_name
                )
                return response
            except Exception as e:
                if not self._retry_exponential_backoff(attempt, e):
                    print(f"Error getting text embedding: {e}")
                    raise e
        return {"status": "Error"}

    def get_image_embedding(self, image_path, input_type="DOCUMENT"): 
        """
        Args:
            image_path: Path to the image file.
            input_type: "TEXT", "QUERY", "DOCUMENT"
        
        """
        data_url = encode_image(image_path)
        for attempt in range(self.max_retries):
            try:
                response = self.client.embed(
                    input=[data_url],
                    input_type=EmbeddingInputType[input_type],
                    model=self.deployment_name
                )   
                return response
            except Exception as e:
                if not self._retry_exponential_backoff(attempt, e):
                    print(f"Error getting image embedding: {e}")
                    raise e
        return {"status": "Error"}

    def cosine_similarity(self, vector1, vector2):
        return np.dot(vector1, vector2) / (np.linalg.norm(vector1) * np.linalg.norm(vector2))

    def _retry_exponential_backoff(self, retry_times: int, exception: Exception):
        """
        Retry mechanism with exponential backoff for handling rate limit exceptions (429).
        """
        if retry_times >= self.max_retries:
            print(f"Max retries reached. Last exception: {exception}")
            return False
        if "429" not in str(exception):
            print(f"Non-retryable exception encountered: {exception}")
            return False
        wait_time = (2 ** retry_times) + random.uniform(0, 1)
        print(f"Retrying in {wait_time:.2f} seconds... (Attempt {retry_times + 1}/{self.max_retries})")
        time.sleep(wait_time)
        return True