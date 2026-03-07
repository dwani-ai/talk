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

Run `vllm serve MODEL_NAME ...` (one `vllm` only; model as positional argument).

docker compose vllm.yml up -d

Qwen/Qwen3.5-2B

Qwen/Qwen3.5-0.8B


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


vllm serve Qwen/Qwen3.5-0.8B \
  --language-model-only \
  --reasoning-parser qwen3 \
  --host 0.0.0.0 \
  --port 8000


docker run --rm --runtime=nvidia --gpus all \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  vllm serve Qwen/Qwen3.5-0.8B \
    --language-model-only \
    --reasoning-parser qwen3 \
    --host 0.0.0.0 \
    --port 8000
