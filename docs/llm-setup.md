LLM Setup

With llama-cpp

python3.10 -m venv venv
source venv/bin/activate
pip install hf_cli

hf download google/gemma-4-E2B-it \
  --local-dir ./models

docker compose -f text-qwen-llama-cpp.yml up -d


---

with vllm

Run `vllm serve MODEL_NAME ...` (one `vllm` only; model as positional argument).

docker compose vllm.yml up -d

google/gemma-4-E2B-it


--
Text only

vllm serve google/gemma-4-E2B-it \
  --language-model-only \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --enable-prefix-caching \
  --enable-auto-tool-choice

Multimodal -  

vllm serve google/gemma-4-E2B-it \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --enable-prefix-caching \
  --enable-auto-tool-choice


vllm serve google/gemma-4-E2B-it \
  --language-model-only \
  --reasoning-parser gemma4 \
  --tool-call-parser gemma4 \
  --host 0.0.0.0 \
  --port 8000


docker run --rm --runtime=nvidia --gpus all \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  vllm serve google/gemma-4-E2B-it \
    --language-model-only \
    --reasoning-parser gemma4 \
    --tool-call-parser gemma4 \
    --host 0.0.0.0 \
    --port 8000
