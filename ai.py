import os
from google import genai


API_KEY = ""  # <-- Put your actual API key here

client = genai.Client(api_key=API_KEY)

def get_ai_response(question):
    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=question
        )
        return response.text
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    print(get_ai_response("Hello! Are you working?"))
