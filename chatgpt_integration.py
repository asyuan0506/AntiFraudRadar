from openai import OpenAI
import base64
import dotenv, os
from utils.image_utils import encode_image, decode_image

dotenv.load_dotenv()

class ChatGPTClient:
    api_key = os.getenv("OPENAI_API_KEY")
    def __init__(self, model: str = "gpt-5-nano"):
        self.client = OpenAI(api_key=ChatGPTClient.api_key)
        self.model = model

    def generate_response(self, user_text="", image_path=None):
        response = self.client.responses.create(
            model=self.model,
            instructions="你是一位防詐騙專家，你要根據使用者的輸入提供有用的建議和資訊。你要讓你的回答簡潔。若與防詐騙無關，請禮貌地告知使用者你只能提供防詐騙相關的協助。",
            input=self._generate_input(user_text, image_path=image_path), #type: ignore
            stream=False, # Set to True for streaming responses
            max_output_tokens=4096,
        ) # type: ignore

        return response.output_text

    def _generate_input(self, user_input, image_path=None, retrieved_context=None): #TODO: Put similar chunks in
        input_template = f"""
            請根據以下相關資訊來回答問題。此外，這是單輪對話。
            --- 相關資訊 ---
            {retrieved_context}
            ---
            問題：
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

    user_input = "請幫我看看這張圖片，這是我收到的簡訊內容，我想知道這是不是詐騙？"
    image_path = "images/fraud_message.png"

    try:
        response = chatgpt_client.generate_response(user_input=user_input, image_path=image_path)
        print(response)
    except Exception as e:
        print(f"Error occurred: {e}")
