from langchain_text_splitters import RecursiveCharacterTextSplitter

def split_text_into_chunks(text, chunk_size=1000, chunk_overlap=200):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, 
        chunk_overlap=chunk_overlap,
        )
    return text_splitter.split_text(text)

if __name__ == "__main__":
    with open("texts/test_news.txt", "r", encoding="utf-8") as file:
        document = file.read()
    texts = split_text_into_chunks(document)
    for i, chunk in enumerate(texts):
        print(f"--- Chunk {i+1} ---")
        print(chunk)