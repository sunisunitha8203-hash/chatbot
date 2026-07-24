from ai import get_ai_response

question = input("Ask your question: ")

answer = get_ai_response(question)

print("\nAI Answer:\n")
print(answer)