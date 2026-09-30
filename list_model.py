from core.ollama_client import detect_ollama_models


if __name__ == "__main__":
    status = detect_ollama_models()
    print(status["message"])
    for model in status["models"]:
        print(model)