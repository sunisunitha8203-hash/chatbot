from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

def get_ai_response(question):
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=question
        )
        return response.text
    except Exception as e:
        return f"Error: {e}"