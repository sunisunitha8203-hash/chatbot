from flask import Flask, render_template, request, jsonify, redirect, session
from ai import get_ai_response
import sqlite3
import markdown

app = Flask(__name__)
app.secret_key = "student_chatbot_secret_key"
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
    return render_template("chat.html")

# AI Chat API with Database Logging
@app.route("/ask", methods=["POST"])
def ask():

    if "email" not in session:
        return jsonify({"answer": "Please login first."})

    data = request.get_json()
    question = data["question"]

   
    answer = get_ai_response(question)

    
    answer_html = markdown.markdown(answer)

    
    conn = sqlite3.connect("chatbot.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO chats(student_email, question, answer) VALUES(?,?,?)",
        (session["email"], question, answer)
    )

    conn.commit()
    conn.close()

   
    return jsonify({
        "answer": answer_html
    })
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
