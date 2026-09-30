from core.ollama_client import detect_ollama_models, generate_grounded_answer


def get_ai_response(question, sources, temperature=0.2, model=None):
    """Generate an answer only from chunks retrieved from uploaded documents."""
    if model is None:
        model_status = detect_ollama_models()
        if not model_status["connected"] or not model_status["model"]:
            raise RuntimeError(model_status["message"])
        model = model_status["model"]
    return generate_grounded_answer(
        question, sources, model, temperature=temperature
    )