from google import genai
import os, dotenv

dotenv.load_dotenv() 
gemini_embeddings_api_key = os.getenv("GEMENI_EMBEDDINGS_API_KEY")

client = genai.Client(api_key=gemini_embeddings_api_key)

''' 建立單一區塊做為字串傳遞，一次產生 embeddings
result = client.models.embed_content(
        model="gemini-embedding-001",
        contents="What is the meaning of life?")

print(result.embeddings)
'''

''' 建立多個區塊做為字串清單傳遞，一次產生 embeddings
result = client.models.embed_content(
        model="gemini-embedding-001",
        contents= [
            "What is the meaning of life?",
            "What is the purpose of existence?",
            "How do I bake a cake?"
        ])

for embedding in result.embeddings:
    print(embedding)
'''