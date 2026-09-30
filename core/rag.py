import math

from core.document_processing import chunk_pages


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class LocalEmbedder:
    def __init__(self, model_name=EMBEDDING_MODEL):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "Install the sentence-transformers package to generate local embeddings."
            ) from error
        self.model = SentenceTransformer(model_name, device="cpu")

    def encode(self, texts):
        vectors = self.model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return [vector.tolist() for vector in vectors]


class DocumentIndex:
    def __init__(self, embedder=None):
        self.embedder = embedder or LocalEmbedder()
        self.chunks = []
        self.vectors = []
        self.documents = {}

    def add_document(self, source, pages, chunk_size=700, overlap=100):
        chunks = chunk_pages(pages, source, chunk_size, overlap)
        if not chunks:
            raise ValueError("The document did not contain enough text to create chunks.")
        vectors = self.embedder.encode([chunk["text"] for chunk in chunks])
        if len(vectors) != len(chunks) or any(not vector for vector in vectors):
            raise ValueError("The embedding model returned an invalid vector array.")

        self.remove_document(source)
        self.chunks.extend(chunks)
        self.vectors.extend(vectors)
        self.documents[source] = {
            "characters": sum(len(item["text"]) for item in pages),
            "pages": len(pages),
            "chunks": len(chunks),
        }
        return self.documents[source]

    def remove_document(self, source):
        if source not in self.documents:
            return
        keep = [index for index, chunk in enumerate(self.chunks) if chunk["source"] != source]
        self.chunks = [self.chunks[index] for index in keep]
        self.vectors = [self.vectors[index] for index in keep]
        del self.documents[source]

    def retrieve(self, question, top_k=3, threshold=0.2):
        if not self.chunks:
            return []
        if not 1 <= top_k <= 10:
            raise ValueError("Top-K must be between 1 and 10.")
        if not 0 <= threshold <= 1:
            raise ValueError("Similarity threshold must be between 0 and 1.")

        query_vector = self.embedder.encode([question])[0]

        def cosine_similarity(vector):
            if len(vector) != len(query_vector):
                raise ValueError("Embedding vectors have inconsistent dimensions.")
            numerator = sum(left * right for left, right in zip(vector, query_vector))
            denominator = math.sqrt(sum(value * value for value in vector)) * math.sqrt(
                sum(value * value for value in query_vector)
            )
            return numerator / denominator if denominator else 0.0

        scores = [cosine_similarity(vector) for vector in self.vectors]
        ranked = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)
        results = []
        seen_text = set()
        for index in ranked:
            score = float(scores[index])
            chunk = self.chunks[index]
            normalized_text = " ".join(chunk["text"].lower().split())
            if score < threshold or normalized_text in seen_text:
                continue
            seen_text.add(normalized_text)
            results.append({**chunk, "similarity": score})
            if len(results) == top_k:
                break
        return results