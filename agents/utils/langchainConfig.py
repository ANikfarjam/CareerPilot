from langchain_huggingface import ChatHuggingFace, HuggingFacePipeline

from transformers import pipeline
import torch

model_id = "openai/gpt-oss-120b"

pipe = pipeline(
    "text-generation",
    model=model_id,
    torch_dtype="auto",
    device_map="cuda",
    # Without it generate() falls back to max_length=20 tokens total; gpt-oss
    # also spends part of the budget on its analysis channel before answering.
    max_new_tokens=4096,
)

llm = HuggingFacePipeline(pipeline=pipe)

# ChatHuggingFace applies the model's chat template and exposes the
# standard BaseChatModel interface (.invoke, .stream, .bind_tools),
# which is what LangGraph agents expect.
chat_model = ChatHuggingFace(llm=llm)