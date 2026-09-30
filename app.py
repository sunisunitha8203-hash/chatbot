import os
import sqlite3

from flask import Flask, render_template, request, jsonify, redirect, session
from werkzeug.utils import secure_filename

from ai import get_ai_response
from core.document_processing import clean_text, extract_document
from core.ollama_client import detect_ollama_models
from core.rag import DocumentIndex, LocalEmbedder

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "local-workshop-development-key")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

document_indexes = {}
shared_embedder = None


def get_document_index(email):
    global shared_embedder
    if email not in document_indexes:
        if shared_embedder is None:
            shared_embedder = LocalEmbedder()
        document_indexes[email] = DocumentIndex(shared_embedder)
    return document_indexes[email]
# Home Page
@app.route("/")
def home():
    return render_template("index.html")

# Login Page
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM students WHERE email=? AND password=?",
            (email, password)
        )

        user = cursor.fetchone()

        conn.close()

        if user:
            session["email"] = email
            return redirect("/chat")
        else:
            return "Invalid Email or Password!"
    return render_template("login.html")

#logout    
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")

# Registration Page
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        
        try:
            with sqlite3.connect("chatbot.db", timeout=10) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    "INSERT INTO students(name, email, password) VALUES(?,?,?)",
                    (name, email, password)
                )
                conn.commit()
                
                session["email"] = email
                return redirect("/chat")

        except sqlite3.IntegrityError:
           
            return "Error: That email address is already registered.", 400

        except sqlite3.OperationalError as e:
            
            return f"Database busy: {e}. Please try again in a moment.", 500

   
    return render_template("register.html") 

# Chat Page
@app.route("/chat")
def chat():
    if "email" not in session:
        return redirect("/login")
    return render_template("chat.html", student_email=session["email"])


@app.route("/status")
def status():
    if "email" not in session:
        return jsonify({"error": "Please login first."}), 401
    index = document_indexes.get(session["email"])
    ollama = detect_ollama_models()
    documents = index.documents if index else {}
    return jsonify({
        "ollama": ollama,
        "documents": documents,
        "document_count": len(documents),
        "chunk_count": len(index.chunks) if index else 0,
        "embedding_model": "all-MiniLM-L6-v2",
    })


@app.route("/upload", methods=["POST"])
def upload_document():
    if "email" not in session:
        return jsonify({"error": "Please login first."}), 401
    uploaded = request.files.get("document")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Choose a PDF or DOCX file to upload."}), 400
    filename = secure_filename(uploaded.filename)
    if not filename.lower().endswith((".pdf", ".docx")):
        return jsonify({"error": "Only PDF and DOCX files are supported."}), 400

    try:
        chunk_size = int(request.form.get("chunk_size", 700))
        overlap = int(request.form.get("overlap", 100))
        pages = extract_document(filename, uploaded.read())
        index = get_document_index(session["email"])
        stats = index.add_document(filename, pages, chunk_size, overlap)
    except (ValueError, RuntimeError) as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        app.logger.exception("Document processing failed")
        return jsonify({"error": "Document processing failed. Check the file and installed dependencies."}), 500
    return jsonify({"filename": filename, **stats})

# AI Chat API with Database Logging
@app.route("/ask", methods=["POST"])
def ask():

    if "email" not in session:
        return jsonify({"error": "Please login first."}), 401
    data = request.get_json(silent=True) or {}
    question = clean_text(str(data.get("question", "")))
    if not question:
        return jsonify({"error": "Enter a question about your uploaded documents."}), 400
    index = document_indexes.get(session["email"])
    if not index or not index.chunks:
        return jsonify({"error": "Upload and index a PDF or DOCX before asking a question."}), 400
    try:
        top_k = int(data.get("top_k", 3))
        threshold = float(data.get("threshold", 0.2))
        temperature = float(data.get("temperature", 0.2))
        if not 0 <= temperature <= 1:
            raise ValueError("Temperature must be between 0 and 1.")
        sources = index.retrieve(question, top_k=top_k, threshold=threshold)
        if not sources:
            return jsonify({
                "answer": "I did not find relevant information in the uploaded documents. Try asking about a topic they cover.",
                "sources": [],
                "model": None,
            })
        ollama = detect_ollama_models()
        if not ollama["connected"] or not ollama["model"]:
            raise RuntimeError(ollama["message"])
        answer = get_ai_response(
            question, sources, temperature=temperature, model=ollama["model"]
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception as error:
        app.logger.warning("Local answer generation failed: %s", error)
        return jsonify({"error": str(error) or "Could not generate a local answer."}), 503

    
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO chats(student_email, question, answer) VALUES(?,?,?)",
        (session["email"], question, answer)
    )

    conn.commit()
    conn.close()

   
    return jsonify({
        "answer": answer,
        "sources": sources,
        "model": ollama["model"],
    })


@app.route("/clear-documents", methods=["POST"])
def clear_documents():
    if "email" not in session:
        return jsonify({"error": "Please login first."}), 401
    document_indexes.pop(session["email"], None)
    return jsonify({"message": "Document index cleared."})


@app.errorhandler(413)
def upload_too_large(_error):
    return jsonify({"error": "Files must be smaller than 20 MB."}), 413
@app.route("/history")
def history():

    if "email" not in session:
        return redirect("/login")

    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT question, answer FROM chats WHERE student_email=?",
        (session["email"],)
    )

    chats = cursor.fetchall()

    conn.close()

    return render_template("history.html", chats=chats)
@app.route("/profile")
def profile():

    if "email" not in session:
        return redirect("/login")

    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name, email FROM students WHERE email=?",
        (session["email"],)
    )

    student = cursor.fetchone()

    cursor.execute(
        "SELECT COUNT(*) FROM chats WHERE student_email=?",
        (session["email"],)
    )

    total = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "profile.html",
        student=student,
        total=total
    )
if __name__ == "__main__":
    app.run(debug=True)
