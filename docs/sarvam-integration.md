Sarvam Integration

python3.10 -m venv venv
source venv/bin/activate

pip install hf_cli

hf download sarvamai/sarvam-30b-gguf --local-dir models


docker compose -f llama-cpp-sarvam.yml up -d

export LITELLM_MODEL_NAME="openai/sarvam-30b-Q4_K_M.gguf-00001-of-00006.gguf"
export LITELLM_API_BASE="https://qwen-api"
export LITELLM_API_KEY="sk-dummy"


 