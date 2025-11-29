from dotenv import load_dotenv
import os
import requests, json

load_dotenv()

class TTSClient:
    endpoint = "https://ntpuf-mikgdxgz-eastus2.cognitiveservices.azure.com/openai/deployments/gpt-4o-mini-transcribe/audio/transcriptions?api-version=2025-03-01-preview"
    api_key = os.getenv("GPT_TTS_API_KEY")
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
        self.data = {
            "model": "gpt-4o-mini-transcribe",
        }

    def transcribe_audio(self, audio_file_path):
        with open(audio_file_path, "rb") as audio_file:
            files = {
                "file": audio_file
            }
            response = requests.post(self.endpoint, headers=self.headers, data=self.data, files=files)
            if response.status_code == 200:
                return response.json()
            else:
                raise Exception(f"Error {response.status_code}: {response.text}")
            
if __name__ == "__main__":
    print("TTS Client Test")
    tts_client = TTSClient()
    transcription = tts_client.transcribe_audio("audios/test_audio.mp3")
    print(json.dumps(transcription, indent=2, ensure_ascii=False))