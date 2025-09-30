import os, dotenv
from flask import Flask, request, abort

# 載入 json 標準函式庫，處理回傳的資料格式
import json

# 載入 LINE Message API 相關函式庫 (v3)
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent


app = Flask(__name__)


# 初始化 LINE Bot
dotenv.load_dotenv()  # 讀取 .env 檔案
configuration = Configuration(access_token=os.getenv("CHANNEL_ACCESS_TOKEN"))
channel_secret = os.getenv("CHANNEL_SECRET")
handler = WebhookHandler(channel_secret)

@app.route("/", methods=['POST'])
def linebot():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)                    # 取得收到的訊息內容

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        
        # 取得收到的訊息
        msg = event.message.text
        print(f"收到訊息: {msg}")
        
        # 準備回覆訊息
        reply = msg  # 簡單回傳相同訊息
        
        #回傳訊息
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=reply)],
                notificationDisabled=False
            )
        )

if __name__ == "__main__":
    app.run()