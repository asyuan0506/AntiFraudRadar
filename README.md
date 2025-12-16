# 🛡️ AntiFraudRadar: Multi-modal Anti-Scam Line Bot

> A real-time anti-fraud detection Line Bot powered by Multi-modal RAG and Azure Cosmos DB.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![LangChain](https://img.shields.io/badge/LangChain-Framework-green)](https://www.langchain.com/)
[![Azure Cosmos DB](https://img.shields.io/badge/Azure-Cosmos%20DB-0078D4)](https://azure.microsoft.com/en-us/services/cosmos-db/)
[![Cohere](https://img.shields.io/badge/Cohere-Embed%20v3-purple)](https://cohere.com/)

## 📖 Introduction

**AntiFraudRadar** is a Line Bot application integrating Large Language Models (LLM) with a real-time news database. It is designed to tackle rapidly evolving scam tactics that traditional keyword-based filters fail to catch.

By leveraging an advanced **RAG (Retrieval-Augmented Generation)** architecture with **Multi-modal** capabilities, the system allows users to forward suspicious text messages or images (e.g., fraudulent flyers, fake QR codes). The bot verifies this input against a vector database of the latest anti-scam news and provides evidence-based warnings and advice.

## 🚀 Key Features

* **Multi-modal Detection**: Supports both text and image inputs, capable of identifying visual scam indicators (e.g., fake logos, manipulated screenshots).
* **Precision Retrieval (2-Stage Strategy)**:
    * Implements an **Image-Guided Hierarchical Retrieval** strategy.
    * **Stage 1 (Coarse)**: Uses image vectors to scope the search to specific relevant news articles.
    * **Stage 2 (Fine)**: Performs a focused text search within that scope to retrieve precise details, significantly reducing **retrieval noise** and **LLM hallucinations**.
* **Real-time Data Updates**: A backend crawler continuously monitors trusted sources (e.g., CIB, TVBS News), cleaning and vectorizing data into the system.
* **Explainable AI**: Responses include citations and links to original news sources, ensuring transparency and trust.

## 🏗️ System Architecture

This project is built on **Azure Cosmos DB for NoSQL** as the vector store, utilizing **Cohere Embed v3/v4** models for high-quality semantic embeddings.

### Data Pipeline
1.  **ETL Crawler**: Scrapes news articles -> Cleans HTML -> Parses text and images.
2.  **Structuring**: Converts data into JSONL format, linking `Text Chunks` and `Image Items` via a common `article_id`.
3.  **Embedding**: Uses Cohere API to vectorize text (token-based splitting) and images respectively.
4.  **Indexing**: Ingests data into Azure Cosmos DB with vector indexing enabled.

### Retrieval Strategy (The "Secret Sauce")
To solve the "modality gap," we implement a **Coarse-to-Fine** workflow for image queries:

1.  **Stage 1 (Image Search)**: User uploads an image -> Vector Search identifies similar `Image Items` -> Extracts the parent `article_id`.
2.  **Stage 2 (Scoped Text Search)**: The system locks the scope to the identified `article_id` -> Performs a second vector search to find the most relevant `Text Chunks` explaining the scam.
3.  **Generation**: The retrieved text chunks are fed into the LLM to generate the final response.



## 🛠️ Tech Stack

* **Backend**: Python, Flask / FastAPI
* **Bot Framework**: Line Messaging API
* **LLM Orchestration**: LangChain
* **Embedding Model**: Cohere `embed-multilingual-v4.0`
* **Vector Database**: Azure Cosmos DB for NoSQL (Vector Search enabled)
* **Crawler**: Python (`requests`, `BeautifulSoup`), JSONL output

## 📂 Database Schema Example

We use a single-container strategy in Cosmos DB, distinguishing items via a `type` field:

```json
// Text Chunk Item
{
  "id": "news_123_text_0",
  "type": "text_chunk",
  "articleId": "news_123",
  "content": "Scammers are recently using fake tax rebate...",
  "content_vector": [0.12, 0.34, ...],
  "metadata": { ... }
}

// Image Item
{
  "id": "news_123_img_0",
  "type": "image_item",
  "articleId": "news_123",
  "image_url": "s3://path/to/img.jpg",
  "content_vector": [0.98, 0.76, ...],
  "metadata": { ... }
}
```

📝 Getting Started
------------------

### Prerequisites

-   Python 3.9+

-   Line Developer Account

-   Azure Cosmos DB Account

-   Cohere API Key

### Installation

1.  Clone the repo
    ```
    git clone [https://github.com/asyuan0506/AntiFraudRadar.git]
    ```

2.  Install packages
    ```
    pip install -r requirements.txt

    ```

3.  Setup environment variables (`.env`)

    ```
    LINE_CHANNEL_ACCESS_TOKEN=...
    LINE_CHANNEL_SECRET=...
    COHERE_API_KEY=...
    AZURE_COSMOS_ENDPOINT=...
    AZURE_COSMOS_KEY=...
    ...
    ```

4.  Run the application
    ```
    python app.py
    ```
