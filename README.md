Talk - dwani.ai

Try at [https://talk.dwani.ai](https://talk.dwani.ai) 


Conversational AI for Indian languages

Built with motivation to make AI accessible and available to everyone. 

Runs with open-weight models using Nvidia L4 GPU on Google Cloud.


Would love to get feedback and how you would use it for your own ideas ? 

---


## Run locally (Python)

Use `0.0.0.0` when TTS/ASR/LLM run on the same machine:

```bash
export DWANI_API_BASE_URL_TTS="http://0.0.0.0:10804"
export DWANI_API_BASE_URL_ASR="http://0.0.0.0:10803"
export DWANI_API_BASE_URL_LLM="http://0.0.0.0:10802"
python3.10 -m venv venv
source venv/bin/activate
python main.py
```

## Run with Docker (UI + backend)

When the app runs **inside Docker** but TTS/ASR/LLM run on the **host**, use `host.docker.internal` so the container can reach the host:

```bash
cp .env.example .env
# .env already uses host.docker.internal — edit if your ports differ
docker compose up -d
```

Open http://localhost (UI). If you used `0.0.0.0` in `.env`, change it to `http://host.docker.internal:PORT` for each service.

## Test (curl)

```bash
curl -X POST 'http://localhost:8001/v1/speech_to_speech?language=kannada' \
  -H 'Content-Type: multipart/form-data' -F 'file=@kannada_sample.wav' -o test.mp3
```

<!-- 
export TTS_NFE_STEPS=16  
nohup python src/server/main.py --host 0.0.0.0 --port 10804 > server.log 2>&1 &


nohup python src/server/asr_api.py --port 10803 --host 0.0.0.0 > server.log 2>&1 &
-->