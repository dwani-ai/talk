Sarvam Integration

python3.10 -m venv venv
source venv/bin/activate
mkdir models
pip install hf_cli

hf download sarvamai/sarvam-30b-gguf --local-dir models


docker compose -f llama-cpp-sarvam.yml up -d

export LITELLM_MODEL_NAME="openai/gemma3"
export LITELLM_API_BASE="https://qwen-api"
export LITELLM_API_KEY="sk-dummy"


 