# Document Studio: Local RAG Workshop

A Flask-based “chat with documents” lab. Upload a PDF or DOCX, inspect its extracted text chunks, retrieve relevant chunks with local sentence embeddings and cosine similarity, then ask a local Qwen or Llama model through Ollama to answer from those sources. No hosted LLM, API key, or GPU is required.

## RAG in One Minute

**Document → Extract → Clean → Chunk → Embed → Compare → Retrieve → Context → Ollama → Answer**

- An embedding is a numeric representation of a text's meaning. This project creates embeddings locally with `all-MiniLM-L6-v2`.
- Cosine similarity compares vector direction: `similarity = (a · b) / (||a|| × ||b||)`. Higher scores mean the question and chunk are more semantically alike.
- Retrieval selects the highest-scoring chunks above the chosen threshold. The UI shows their source, page when available, chunk ID, text, and score.
- Generation is a separate step: only the question and retrieved text are sent to Ollama. The LLM does not automatically know the uploaded document.
- Uploaded content is untrusted reference data, not instructions. A similarity threshold that returns no chunks prevents unrelated context being sent to the model.

## Architecture

```text
Browser (templates/chat.html)
   | upload / ask / status
Flask routes (app.py) ---- per-student in-memory indexes
   |                          |
   +-- document_processing.py  +-- rag.py
   |   PyMuPDF / python-docx      MiniLM embeddings + cosine Top-K
   |
   +-- ai.py -> ollama_client.py -> local Ollama -> Qwen preferred / Llama fallback
```

The index is held in process memory and is scoped to the signed-in student. It is cleared when the server restarts; uploaded files are not saved to disk. DOCX page numbers are not available from `python-docx`, so those sources show no page.

## Setup (Windows PowerShell)

Use Python 3.11 for the smoothest compatibility with the local embedding stack.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
```

Install [Ollama for Windows](https://ollama.com/download/windows), start it, then install one model. Qwen is preferred; Llama is a fallback. There is no need to install both.

```powershell
ollama pull qwen2.5:3b
# Or, if you prefer the fallback family:
ollama pull llama3.2:3b
```

Start the Flask application:

```powershell
python app.py
```

Open `http://127.0.0.1:5000`, register or log in, then open the chat. The embedding model is downloaded from Hugging Face on first use and cached locally; this is separate from Ollama and does not use an API key. Later embedding runs use the local cache. Ollama models are never downloaded automatically.

For a stable Flask session key, set `FLASK_SECRET_KEY` in the environment before starting the app. The built-in development value is only suitable for a local workshop.

## Workshop Demo

1. Start Ollama and confirm the model badge shows Qwen or Llama.
2. Upload a college syllabus PDF or DOCX. The index panel reports extracted characters, page count, and chunk count.
3. Ask “What are the eligibility requirements mentioned in this document?”
4. Expand **Retrieved sources** to compare chunk text, metadata, and cosine scores with the answer.
5. Change Top-K or the similarity threshold and ask again to observe retrieval changes.
6. Ask about something absent from the document. A high threshold or unrelated question should produce a “not found” response without calling the LLM.
7. Clear the document index to reset the workshop workspace.

Other useful questions: “What is the application deadline?”, “Which courses are required?”, “Summarize the attendance policy.”

## Tests

Tests use a deterministic fake embedder, so they do not need Ollama or download the sentence-transformer model. PDF/DOCX extraction tests create temporary documents in memory.

```powershell
python -m unittest -v test_ai
```

## Troubleshooting

- **Ollama is not responding:** Start the Ollama application and check `ollama list`. The app uses `http://127.0.0.1:11434`.
- **No supported model:** Install one explicitly, for example `ollama pull qwen2.5:3b` or `ollama pull llama3.2:3b`; refresh the chat page.
- **Embedding model setup fails:** Check internet access for the first model download and available disk space. The model is cached after download.
- **PDF has no selectable text:** It may be scanned/image-only. OCR is not included; use a text-based PDF or OCR it before upload.
- **DOCX page is unavailable:** DOCX paragraph and table text are extracted, but the file format/library does not provide reliable page layout.
- **Upload is rejected:** Only PDF/DOCX files smaller than 20 MB are accepted. Empty documents and invalid chunk settings are rejected with a UI message.
- **Answer generation fails:** Check that the model shown in the header is installed and that the laptop has enough memory. Smaller 3B models are suitable for classroom hardware.

## Main Components

- `app.py`: authenticated Flask endpoints, upload limits, and per-student in-memory indexes.
- `core/document_processing.py`: PDF/DOCX extraction, conservative cleanup, and page-aware word chunks.
- `core/rag.py`: CPU Sentence Transformers embeddings, vector storage, cosine similarity, thresholding, and Top-K retrieval.
- `core/ollama_client.py`: local model discovery, Qwen-first/Llama-fallback selection, and grounded `/api/chat` requests.
- `ai.py`: small generation boundary that requires retrieved sources.
- `templates/chat.html`: upload, settings, chat, status, and transparent source panel.