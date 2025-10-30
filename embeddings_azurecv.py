import os, dotenv
import json
import requests
import numpy as np

dotenv.load_dotenv() 

def vectorize_image(image_url, endpoint=None, subscription_key=None):
    """
    使用 Azure Computer Vision retrieval:vectorizeImage API。
    需要環境變數 COMPUTER_VISION_KEY1 或直接傳入。
    """
    endpoint = endpoint or os.getenv("https://testing1embedding.cognitiveservices.azure.com/")
    subscription_key = subscription_key or os.getenv("COMPUTER_VISION_KEY1")
    if not endpoint or not subscription_key:
        raise ValueError("COMPUTER_VISION_ENDPOINT and COMPUTER_VISION_KEY1 Not Set")

    api_path = "/computervision/retrieval:vectorizeImage"
    params = {
        "api-version": "2024-02-01",
        "model-version": "2023-04-15"
    }
    url = endpoint.rstrip("/") + api_path

    headers = {
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": subscription_key
    }
    data = {"url": image_url}

    resp = requests.post(url, params=params, headers=headers, data=json.dumps(data), timeout=30)
    resp.raise_for_status()

    return resp.json()

def vectorize_text(text, endpoint=None, subscription_key=None):
    """
    使用 Azure Computer Vision retrieval:vectorizeText API。
    需要環境變數 COMPUTER_VISION_ENDPOINT 和 COMPUTER_VISION_KEY，或直接傳入。
    """
    endpoint = endpoint or os.getenv("COMPUTER_VISION_ENDPOINT")
    subscription_key = subscription_key or os.getenv("COMPUTER_VISION_KEY1")
    if not endpoint or not subscription_key:
        raise ValueError("COMPUTER_VISION_ENDPOINT and COMPUTER_VISION_KEY1 Not Set")

    api_path = "/computervision/retrieval:vectorizeText"
    params = {
        "api-version": "2024-02-01",
        "model-version": "2023-04-15"
    }
    url = endpoint.rstrip("/") + api_path

    headers = {
        "Content-Type": "application/json",
        "Ocp-Apim-Subscription-Key": subscription_key
    }
    data = {"text": text}

    resp = requests.post(url, params=params, headers=headers, data=json.dumps(data), timeout=30)
    resp.raise_for_status()

    return resp.json()

def cosine_similarity(vector1, vector2):
    return np.dot(vector1, vector2) / (np.linalg.norm(vector1) * np.linalg.norm(vector2))

if __name__ == "__main__":
    sample_url = "https://learn.microsoft.com/azure/ai-services/computer-vision/media/quickstarts/presentation.png"
    #print(vectorize_image(sample_url))
    sample_text = "The latest news highlights significant international efforts to combat organized financial crime, with a focus on sophisticated cyber-enabled scams and the involvement of transnational criminal organizations (TCOs).The U.S. and U.K. recently took their largest-ever action against cybercriminal networks in Southeast Asia, designating a major TCO involved in human trafficking, forced labor, and pig butchering scams, which have cost victims billions. This network uses elaborate schemes to cultivate trust and induce victims to invest in fraudulent platforms.Globally, law enforcement operations like Interpol's HAECHI VI have recovered hundreds of millions of dollars by targeting seven types of cybercrime, including romance scams, investment fraud, and money laundering. In Europe, an operation called SIMCARTEL dismantled a cybercrime-as-a-service network that provided infrastructure (like 40,000 active SIM cards) for various frauds, including daughter-son scams and fake investment offers.Technology continues to enable new fraud vectors, with news reporting that Chinese fraudsters are using deepfake videos of investment analysts on social media, often placed via complicit local digital advertising agencies, to lure Indian victims into share trading scams.In response, major tech companies like Meta are rolling out new protective features, such as screen-sharing alerts on WhatsApp and enhanced scam detection on Messenger, especially to safeguard vulnerable groups like senior citizens. Governments are also intensifying their focus; Canada announced a new Anti-Fraud Strategy and a dedicated Financial Crimes Agency to address a nearly 300% increase in reported losses since 2020. Regulators in the U.K. are pushing banks for stricter controls against romance fraud, noting missed red flags in cases where victims lost huge sums through relationships initiated on social media and dating apps."
    print(len(vectorize_text(sample_text)['vector']))