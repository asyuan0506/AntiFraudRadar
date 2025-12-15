from openai import OpenAI
import base64
import dotenv, os
from utils.image_utils import encode_image, decode_image

dotenv.load_dotenv()

class ChatGPTClient:
    def __init__(self, model: str = "gpt-5-nano"):
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate_response(self, user_text="", image_path=None, retrieved_context=None, mode: str = "TEXT"):
        """Generate a response from the ChatGPT model based on user input and optional image.
         Args:
            user_text (str): The text input from the user.
            image_path (str, optional): Path to an image file to include in the input.
            retrieved_context (str, optional): Additional context to provide to the model.
            mode (str): Mode of operation, either "TEXT" or "IMAGE" or "AUDIO".
        """
        instructions = """
        你是一位精準的防詐騙判斷助手。你的目標是快速判斷風險。
        
        【判斷原則】
        1. 不要對正常對話或官方通知產生過度反應。
        
        【回答限制】
        1. 回答必須極度簡潔，控制在 200 字以內。
        2. 不要輸出通用的防詐騙衛教資訊，只針對該訊息回應。
        3. 直接給出結論。
        """
        if mode == "IMAGE":
            instructions += " (針對圖片：請檢查是否有偽造痕跡或詐騙關鍵字)"
        elif mode == "AUDIO":
            instructions += " (針對音訊：請分析語氣、是否詐騙話術。)"

        response = self.client.responses.create(
            model=self.model,
            reasoning={"effort": "medium"},
            instructions=instructions,
            input=self._generate_input(user_text, 
                                       image_path=image_path, 
                                       retrieved_context=retrieved_context), #type: ignore
            stream=False, # Set to True for streaming responses
            max_output_tokens=4096,
        ) # type: ignore

        return response.output_text

    def _generate_input(self, user_input, image_path=None, retrieved_context=None):
        input_template = f"""
            請依照以下格式回答：
            【風險等級】：(高風險 / 可疑 / 低風險)
            【分析】：(一句話說明原因)
            【建議】：(一句話建議行動)
            【補充資訊】：(可以結合相關資訊提供額外說明，也可不提供)
            請根據以下相關資訊來回答問題:
            --- 相關資訊 ---
            {retrieved_context}
            ---
            使用者訊息：
            {user_input}
            """
        content = [{"type": "input_text", "text": input_template}]

        if image_path:
            try:
                image_data_url = encode_image(image_path)
                content = [
                {
                    "type": "input_text", "text": input_template
                },
                {
                    "type": "input_image",
                    "image_url": image_data_url
                }]
            except Exception as e:
                print(f"Error encoding image: {e}")
                image_data_url = None

        generated_input = [
            {
                "role": "user",
                "content": content
            }
        ]
        return generated_input
    
if __name__ == "__main__":
    print("ChatGPT Client Test")
    chatgpt_client = ChatGPTClient()

    user_text = """
    您好！我們正協助處理大量網路詐騙案件，因國際反詐力度提升，僅今年在台灣已成功幫助133481人追回失去的資金。

    ⚠️ 若您近期曾接觸以下高風險項目，請務必提高警覺：
    股票投資、虛擬貨幣、跨境電商、刷單、抽獎活動、靈骨塔、生基、骨灰罐、茶葉買賣、古董、黃金等。

    📌 如果您已懷疑或確定遭遇詐騙，但報案後遲遲無法獲得協助，並且仍保留以下資料：
    ✔️ 對話紀錄
    ✔️ 收款帳號
    ✔️ 加密錢包地址
    ✔️ 詐騙網站資訊

    我們可為您免費進行 初步調查與金流追蹤分析。

    ✅ 不收取任何前期費用
    ✅ 成功協助追回到達帳戶後才收取服務費
    ✅ 全程保密，安全可靠，讓您安心

    【聯絡方式】
    👉LINE ID：@307gliay
    👉https://lin.ee/37qqMwp
    """
    image_path = "images/fraud_message.png"

    try:
        response = chatgpt_client.generate_response(user_text=user_text, image_path=None, mode="TEXT")
        print(response)
    except Exception as e:
        print(f"Error occurred: {e}")
