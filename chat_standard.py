import os, dotenv
from flask import Flask, request, abort
import json
import requests
# LINE Message API (v3)
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, AudioMessageContent

from chatgpt_integration import ChatGPTClient


app = Flask(__name__)
print("Starting ChatGPT Client...")
chatgpt_client = ChatGPTClient()

dotenv.load_dotenv()
# Initialize LINE Bot
channel_access_token = os.getenv("CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("CHANNEL_SECRET")
configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

@app.route("/", methods=['POST'])
def linebot():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)  # Get the received message content

    try:
        print(body)
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
        print(f"Message Received: {msg}")
        
        reply = msg 
        
        # Reply message
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=reply)],
                notificationDisabled=False
            )
        )
@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event): #TODO: Handle multiple images using imageSet.index
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        msg = event.message
        print(f"Image Received: {msg}")

        reply = "Image received"
        file_data = get_file(msg.id)
        if file_data:
            with open(f"images/received/{msg.id}.jpg", "wb") as f:
                f.write(file_data)
        # Reply message
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=reply)],
                notificationDisabled=False
            )
        )
@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        msg = event.message
        print(f"Audio Received: {msg}")
        
        status = verify_video_audio_prepared(msg.id)
        
        reply = "Audio received"

        # Reply message
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=reply)],
                notificationDisabled=False
            )
        )

def get_file(message_id):
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    headers = {
        'Authorization': f'Bearer {channel_access_token}'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print(response.content)
        return response.content
    elif response.status_code == 202:
        print("File is being prepared, please try again later.") #TODO: implement retry mechanism
    else:
        print(f"Failed to get file: {response.status_code} - {response.text}")
    return None

def verify_video_audio_prepared(message_id):
    url = "https://api-data.line.me/v2/bot/message/{messageId}/content/transcoding"
    headers = {
        'Authorization': f'Bearer {channel_access_token}'
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print(response.content)

    return None # TODO: String return


if __name__ == "__main__":
    try:
        app.run()
    except Exception as e:
        print(f"Error occured: {e}")