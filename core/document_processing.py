import re
from io import BytesIO


def clean_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    paragraphs = []
    current_lines = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            current_lines.append(line)
        elif current_lines:
            paragraphs.append(" ".join(current_lines))
            current_lines = []
    if current_lines:
        paragraphs.append(" ".join(current_lines))
    return "\n\n".join(paragraphs)


def extract_document(filename, content):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    pages = []
    try:
        if extension == "pdf":
            import pymupdf

            with pymupdf.open(stream=content, filetype="pdf") as document:
                pages = [
                    {"page": page_number, "text": page.get_text("text")}
                    for page_number, page in enumerate(document, start=1)
                ]
        elif extension == "docx":
            from docx import Document

            document = Document(BytesIO(content))
            text_parts = [paragraph.text for paragraph in document.paragraphs]
            text_parts.extend(
                "\n".join("\t".join(cell.text for cell in row.cells) for row in table.rows)
                for table in document.tables
            )
            pages = [{"page": None, "text": "\n\n".join(text_parts)}]
        else:
            raise ValueError("Only PDF and DOCX documents are supported.")
    except ImportError as error:
        package = "PyMuPDF" if extension == "pdf" else "python-docx"
        raise RuntimeError(f"Install the {package} package to read this document.") from error
    except Exception as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError(f"Could not read {filename}. Check that the file is valid.") from error

    cleaned_pages = [
        {"page": item["page"], "text": clean_text(item["text"])}
        for item in pages
    ]
    if not any(item["text"] for item in cleaned_pages):
        raise ValueError(
            "No selectable text was found. This may be an image-only PDF; OCR is not enabled."
        )
    return cleaned_pages


def chunk_pages(pages, source, chunk_size=700, overlap=100):
    if chunk_size < 50 or chunk_size > 5000:
        raise ValueError("Chunk size must be between 50 and 5000 words.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk overlap must be smaller than the chunk size.")

    chunks = []
    for item in pages:
        words = item["text"].split()
        step = chunk_size - overlap
        for start in range(0, len(words), step):
            chunk_words = words[start : start + chunk_size]
            if not chunk_words:
                continue
            page_label = f"p{item['page']}" if item["page"] is not None else "doc"
            chunks.append(
                {
                    "chunk_id": f"{source}::{page_label}::{len(chunks) + 1:03d}",
                    "source": source,
                    "page": item["page"],
                    "text": " ".join(chunk_words),
                }
            )
            if start + chunk_size >= len(words):
                break
    return chunks