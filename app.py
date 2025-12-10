import os, dotenv
from flask import Flask, request, abort
import threading
import requests
import time
# LINE Message API (v3)
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, AudioMessageContent

from chatgpt_integration import ChatGPTClient
from tts_integration import TTSClient
from embeddings_cohere import EmbeddingModel
from cosmosdb import CosmosDBClient
from utils.jsonl_parser import JSONLParser
# import multi_site_crawler

app = Flask(__name__)
print("Starting ChatGPT Client...")
chatgpt_client = ChatGPTClient()
print("Starting TTS Client...")
tts_client = TTSClient()
print("Starting Embedding Model...")
embedding_model = EmbeddingModel()
print("Starting CosmosDB Client...")
cosmosdb_client = CosmosDBClient()

crawl_interval = 12 * 60 * 60  # 12 hours

dotenv.load_dotenv()
# Initialize LINE Bot
channel_access_token = os.getenv("CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("CHANNEL_SECRET")
configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

def reply_with_text(reply_token, text):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=reply_token,
                messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
                notificationDisabled=False
            )
        )


@app.route("/", methods=['POST'])
def linebot(): #TODO: Multi-turn conversation 
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)  # Get the received message content TODO: Careful with large inputs

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        msg = event.message.text
        print(f"Message Received")
        retrieved_context, retrieved_news_urls = retrive_content_by_text(msg)

        reply = chatgpt_client.generate_response(user_text=msg, retrieved_context=retrieved_context, mode="TEXT")
        if not reply:
            reply = "Sorry, I couldn't process your request."
        if len(retrieved_context) > 0:
            reply += "\n\n相關新聞:\n" + "\n".join(retrieved_news_urls)

        reply_with_text(event.reply_token, reply)

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event): #TODO: Handle multiple images using imageSet.index
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        msg = event.message
        print(f"Image Received")

        file_data = get_file(msg.id)
        if file_data and isinstance(file_data, bytes):
            path = "images/received"
            if not os.path.isdir(path):
                os.mkdir(path)
            with open(f"{path}/{msg.id}.jpeg", "wb") as f:
                f.write(file_data)
                retrieved_context, retrieved_news_urls = retrive_content_by_image(f"{path}/{msg.id}.jpeg")
                reply = chatgpt_client.generate_response(image_path=f"{path}/{msg.id}.jpeg", retrieved_context=retrieved_context, mode="IMAGE")
                if len(retrieved_news_urls) > 0:
                    reply += "\n\n相關新聞:\n" + "\n".join(retrieved_news_urls)
            os.remove(f"{path}/{msg.id}.jpeg")
        else:
            reply = "Sorry, I couldn't process your image."

        # Reply message
        reply_with_text(event.reply_token, reply)

@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        msg = event.message
        print(f"Audio Received")
        
        status = verify_video_audio_prepared(msg.id)
        file_data = get_file(msg.id)
        max_retries = 10
        while file_data == "preparing" and max_retries > 0:
            time.sleep(0.5)
            file_data = get_file(msg.id)
            max_retries -= 1
        if file_data and isinstance(file_data, bytes):
            path = "audios/received"
            if not os.path.isdir(path):
                os.mkdir(path)
            with open(f"{path}/{msg.id}.m4a", "wb") as audio_bytes_file:
                audio_bytes_file.write(file_data)
                user_text = tts_client.transcribe_audio(f"{path}/{msg.id}.m4a")["text"]
                retrieved_context = retrive_content_by_text(user_text)
                reply = chatgpt_client.generate_response(user_text=user_text, retrieved_context=retrieved_context, mode="AUDIO")
            os.remove(f"{path}/{msg.id}.m4a")
        else:
            reply = "Sorry, I couldn't process your audio message."
        # Reply message
        reply_with_text(event.reply_token, reply)

def get_file(message_id):
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    headers = {
        'Authorization': f'Bearer {channel_access_token}'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.content
    elif response.status_code == 202:
        print("File is being prepared, please try again later.") #TODO: implement retry mechanism
        return "preparing"
    else:
        print(f"Failed to get file: {response.status_code} - {response.text}")
    return None

def verify_video_audio_prepared(message_id):
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content/transcoding"
    headers = {
        'Authorization': f'Bearer {channel_access_token}'
    }

    response = requests.get(url, headers=headers)

    print(response.content) # Status Code

    return None # TODO: String return

def retrive_content_by_text(text: str):
    embedding = embedding_model.get_text_embedding([text], "QUERY").data[0].embedding
    items = cosmosdb_client.query_news_by_vector(embedding, k=5)
    retrieved_context = ""
    retrieved_news_urls = set()
    for item in items:
        if item.get("SimilarityScore", 0.0) <= 0.35:
            continue
        retrieved_context += f"\n- Title: {item.get('title', '')}\n  Content: {item.get('content', '')}\n"
        retrieved_news_urls.add(item.get("url", ""))
    return retrieved_context, retrieved_news_urls

def retrive_content_by_image(image_path: str):
    img_embedding = embedding_model.get_image_embedding(image_path, "QUERY").data[0].embedding
    new_text_query = "這些內容與什麼有關:"
    items = cosmosdb_client.query_news_images_by_image_vector(img_embedding, k=3)
    for item in items:
        new_text_query += f"\n- {item.get('caption', '')} {item.get('alt_text', '')}"
    embedding_new_text = embedding_model.get_text_embedding([new_text_query], input_type="QUERY")
    items = cosmosdb_client.query_news_by_vector(embedding_new_text.data[0].embedding, k=5)
    retrieved_context = ""
    retrieved_news_urls = set()
    for item in items:
        if item.get("SimilarityScore", 0.0) <= 0.35:
            continue
        retrieved_context += f"\n- Title: {item.get('title', '')}\n  Content: {item.get('content', '')}\n"
        news_id = item.get("news_id", "")
        news_item = cosmosdb_client.query_news_by_news_id(news_id)
        if len(news_item) > 0:
            retrieved_news_urls.add(news_item[0].get("url", ""))
    return retrieved_context, retrieved_news_urls

if __name__ == "__main__":
    try:
        # threading.Thread(target=crawl_and_store_news, daemon=True).start() # Deploy as WebJob
        app.run()
    except Exception as e:
        print(f"Error occured: {e}")