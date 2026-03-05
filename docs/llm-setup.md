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


--
Text only

vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
  -dp 8 \
  --enable-expert-parallel \
  --language-model-only \
  --reasoning-parser qwen3 \
  --enable-prefix-caching

Multimodal -  

vllm serve Qwen/Qwen3.5-397B-A17B-FP8 \
  -dp 8 \
  --enable-expert-parallel \
  --mm-encoder-tp-mode data \
  --mm-processor-cache-type shm \
  --reasoning-parser qwen3 \
  --enable-prefix-caching