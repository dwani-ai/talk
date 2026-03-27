Sarvam Integration


python3.10 -m venv venv
source venv/bin/activate

pip install hf_cli

hf download sarvamai/sarvam-30b-gguf --local-dir models


huggingface-cli download sarvamai/sarvam-30b-gguf --local-dir sarvam-30b-gguf


./build/bin/llama-cli \
  -m sarvam-30b-gguf/sarvam-30b-Q4_K_M.gguf-00001-of-00006.gguf \
  -c 4096 \
  -n 512 \
  -p "You are a helpful assistant." \
  --conversation


docker compose -f compose-sarvam-integrated.yml up -d