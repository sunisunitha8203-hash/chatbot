import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from core.document_processing import chunk_pages, clean_text, extract_document
from core.ollama_client import detect_ollama_models
from core.rag import DocumentIndex


class FakeEmbedder:
	def encode(self, texts):
		vectors = []
		for text in texts:
			lowered = text.lower()
			if "calculus" in lowered or "derivative" in lowered:
				vectors.append([1.0, 0.0])
			elif "registration" in lowered:
				vectors.append([0.0, 1.0])
			else:
				vectors.append([0.5, 0.5])
		return vectors


class TextProcessingTests(unittest.TestCase):
	def test_clean_text_preserves_paragraphs_and_joins_hyphenated_lines(self):
		self.assertEqual(
			clean_text("  Course   overview-\ncontinued\x00\n\n  Eligibility   rules "),
			"Course overviewcontinued\n\nEligibility rules",
		)

	def test_chunk_pages_preserves_page_and_source_metadata(self):
		chunks = chunk_pages(
			[{"page": 4, "text": "one two three four five six"}],
			"syllabus.pdf",
			chunk_size=50,
			overlap=10,
		)
		self.assertEqual(len(chunks), 1)
		self.assertEqual(chunks[0]["source"], "syllabus.pdf")
		self.assertEqual(chunks[0]["page"], 4)
		self.assertEqual(chunks[0]["chunk_id"], "syllabus.pdf::p4::001")

	def test_chunking_rejects_invalid_overlap(self):
		with self.assertRaises(ValueError):
			chunk_pages([{"page": None, "text": "some content"}], "notes.docx", 50, 50)

	def test_extracts_pdf_text_and_page_numbers(self):
		import pymupdf

		document = pymupdf.open()
		document.new_page().insert_text((72, 72), "Eligibility requires a completed application.")
		pages = extract_document("syllabus.pdf", document.tobytes())
		document.close()
		self.assertEqual(pages[0]["page"], 1)
		self.assertIn("completed application", pages[0]["text"])

	def test_extracts_docx_paragraphs_and_tables(self):
		from docx import Document

		document = Document()
		document.add_paragraph("Registration closes in June.")
		table = document.add_table(rows=1, cols=1)
		table.cell(0, 0).text = "Bring a student ID."
		content = BytesIO()
		document.save(content)
		pages = extract_document("guide.docx", content.getvalue())
		self.assertIsNone(pages[0]["page"])
		self.assertIn("Registration closes in June.", pages[0]["text"])
		self.assertIn("Bring a student ID.", pages[0]["text"])

	def test_empty_document_fails_with_explanation(self):
		from docx import Document

		content = BytesIO()
		Document().save(content)
		with self.assertRaisesRegex(ValueError, "No selectable text"):
			extract_document("empty.docx", content.getvalue())


class RetrievalTests(unittest.TestCase):
	def setUp(self):
		self.index = DocumentIndex(FakeEmbedder())
		self.index.add_document(
			"math.pdf", [{"page": 2, "text": "Calculus explains the derivative of a function."}]
		)
		self.index.add_document(
			"admin.docx", [{"page": None, "text": "Registration opens in June."}]
		)

	def test_cosine_retrieval_ranks_relevant_source_first(self):
		results = self.index.retrieve("Explain the derivative in calculus", top_k=2)
		self.assertEqual(results[0]["source"], "math.pdf")
		self.assertAlmostEqual(results[0]["similarity"], 1.0)
		self.assertEqual(results[0]["page"], 2)

	def test_threshold_can_return_no_relevant_chunks(self):
		self.assertEqual(self.index.retrieve("unknown topic", threshold=0.99), [])

	def test_top_k_validation(self):
		with self.assertRaises(ValueError):
			self.index.retrieve("calculus", top_k=11)

	def test_replacing_document_replaces_its_vectors(self):
		self.index.add_document(
			"math.pdf", [{"page": 1, "text": "Registration information for students."}]
		)
		self.assertEqual(len(self.index.chunks), 2)
		self.assertEqual(self.index.documents["math.pdf"]["pages"], 1)


class OllamaSelectionTests(unittest.TestCase):
	@staticmethod
	def response(names):
		response = Mock()
		response.json.return_value = {"models": [{"name": name} for name in names]}
		response.raise_for_status.return_value = None
		return response

	@patch("core.ollama_client.requests.get")
	def test_prefers_qwen_over_llama(self, get):
		get.return_value = self.response(["llama3.2:3b", "qwen2.5:3b"])
		result = detect_ollama_models()
		self.assertEqual(result["model"], "qwen2.5:3b")
		self.assertEqual(result["family"], "Qwen")

	@patch("core.ollama_client.requests.get")
	def test_falls_back_to_llama(self, get):
		get.return_value = self.response(["llama3.1:8b"])
		result = detect_ollama_models()
		self.assertEqual(result["model"], "llama3.1:8b")
		self.assertEqual(result["family"], "Llama")

	@patch("core.ollama_client.requests.get")
	def test_no_supported_model_is_a_friendly_status(self, get):
		get.return_value = self.response(["mistral:7b"])
		result = detect_ollama_models()
		self.assertIsNone(result["model"])
		self.assertIn("ollama pull", result["message"])

	@patch("core.ollama_client.requests.get", side_effect=__import__("requests").ConnectionError)
	def test_unavailable_ollama_is_reported(self, _get):
		result = detect_ollama_models()
		self.assertFalse(result["connected"])


class FlaskRouteTests(unittest.TestCase):
	def setUp(self):
		from app import app, document_indexes

		self.app = app
		self.app.config["TESTING"] = True
		self.client = self.app.test_client()
		self.document_indexes = document_indexes
		self.document_indexes.pop("rag-test@example.com", None)

	def tearDown(self):
		self.document_indexes.pop("rag-test@example.com", None)

	def login(self):
		with self.client.session_transaction() as browser_session:
			browser_session["email"] = "rag-test@example.com"

	def test_status_requires_login(self):
		self.assertEqual(self.client.get("/status").status_code, 401)

	def test_chat_page_renders_workshop_interface(self):
		self.login()
		response = self.client.get("/chat")
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"Chat with your documents", response.data)
		self.assertIn(b"Retrieved sources", response.data)

	def test_question_requires_an_indexed_document(self):
		self.login()
		response = self.client.post("/ask", json={"question": "What is the deadline?"})
		self.assertEqual(response.status_code, 400)
		self.assertIn("upload and index", response.json["error"].lower())

	def test_upload_rejects_unsupported_file_type(self):
		self.login()
		response = self.client.post(
			"/upload",
			data={"document": (BytesIO(b"not a supported document"), "notes.txt")},
			content_type="multipart/form-data",
		)
		self.assertEqual(response.status_code, 400)
		self.assertIn("PDF and DOCX", response.json["error"])


if __name__ == "__main__":
	unittest.main()