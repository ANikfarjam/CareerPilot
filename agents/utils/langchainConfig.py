from langchain_ollama import ChatOllama

# Served by the local Ollama server (`just start_llm`), which keeps its weights
# in ./llmModel (`just download_model` pulls them there).
OLLAMA_MODEL = "gpt-oss:20b"
OLLAMA_URL = "http://localhost:11434"

# ChatOllama exposes the standard BaseChatModel interface (.invoke, .stream,
# .bind_tools), which is what LangGraph agents expect.
chat_model = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_URL,
    # Puts gpt-oss's analysis channel in additional_kwargs["reasoning_content"],
    # so .text / .content hold only the final answer.
    reasoning=True,
    # Output budget, shared with the analysis channel (Ollama's default is unlimited).
    num_predict=4096,
    # Ollama's default context is too short for the knowledge-base prompts.
    num_ctx=16384,
    # Keep the weights loaded between calls: reloading 13 GB takes ~2 minutes
    # (Ollama unloads after 5 idle minutes by default).
    keep_alive=-1,
)
