from langchain_ollama import ChatOllama

# Served by the local Ollama server (`just start_llm`), which keeps its weights
# in ./llmModel (`just download_model` pulls them there).
OLLAMA_MODEL = "gpt-oss:20b"
OLLAMA_URL = "http://localhost:11434"
# Ollama's default context is too short for the knowledge-base prompts. A prompt longer than
# NUM_CTX is silently cut from the front (the system prompt goes first), so prompt builders
# keep within PROMPT_BUDGET_TOKENS (agents/resume_builder/guards.py).
NUM_CTX = 16384
# Output budget, shared with the analysis channel (Ollama's default is unlimited).
NUM_PREDICT = 4096
PROMPT_BUDGET_TOKENS = NUM_CTX - NUM_PREDICT

# ChatOllama exposes the standard BaseChatModel interface (.invoke, .stream,
# .bind_tools), which is what LangGraph agents expect.
chat_model = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_URL,
    # Puts gpt-oss's analysis channel in additional_kwargs["reasoning_content"],
    # so .text / .content hold only the final answer.
    reasoning=True,
    num_predict=NUM_PREDICT,
    num_ctx=NUM_CTX,
    # Keep the weights loaded between a run's calls: reloading 13 GB takes ~2 minutes
    # (Ollama unloads after 5 idle minutes by default). Each agent entry point unloads
    # them when its run ends (agents/utils/memory_allocation.release_memory).
    keep_alive=-1,
)
