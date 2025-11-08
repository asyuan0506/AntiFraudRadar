import json
import os

class JSONLParser:
    def __init__(self, file_path):
        self.file_path = file_path
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"The file {file_path} does not exist.")
        self.articles = []

    def parse(self):
        with open(self.file_path, 'r', encoding='utf-8') as file:
            for line in file:
                article = json.loads(line)
                self.articles.append(article)
    
    def get_article_object(self, index, key):
        if index < 0 or index >= len(self.articles):
            raise IndexError("Article index out of range.")
        if key not in self.articles[index]:
            raise KeyError(f"Key '{key}' not found in article.")
        return self.articles[index][key]
    
if __name__ == "__main__":
    parser = JSONLParser("scam_rag_dataset.jsonl")
    parser.parse()
    print(f"Total articles parsed: {len(parser.articles)}")
    print("First article title:", parser.get_article_object(0, "title"))
    print("First article type: ", type(parser.articles[0]))
    print("First article: ", parser.articles[0])