LLM Setup

With llama-cpp

python3.10 -m venv venv
source venv/bin/activate
pip install hf_cli

hf download Qwen/Qwen3-0.6B-GGUF \
  --include "Qwen3-0.6B-Q8_0.gguf" \
  --local-dir ./models

docker compose -f text-qwen-llama-cpp.yml up -d


---

with vllm

docker compose vllm.yml up -d