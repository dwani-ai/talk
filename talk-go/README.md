# talk-go

Go implementation of the dwani.ai Talk API (speech-to-speech with ASR → LLM → TTS).  
Python version remains in the parent directory.

## Endpoint

- **POST /v1/speech_to_speech?language={kannada|hindi|tamil}**  
  - Body: multipart form with `file` (audio file)  
  - Returns: `audio/mp3`

## Environment (required)

| Variable | Description |
|----------|-------------|
| `DWANI_API_BASE_URL_ASR` | ASR service base URL (e.g. `http://host:10803`) |
| `DWANI_API_BASE_URL_TTS` | TTS service base URL (e.g. `http://host:10804`) |
| `DWANI_API_BASE_URL_LLM` | OpenAI-compatible LLM base URL (e.g. `http://host:10802`) |
| `DWANI_LLM_MODEL` | Optional; default `gemma3` |

## Run locally

```bash
export DWANI_API_BASE_URL_TTS="http://0.0.0.0:10804"
export DWANI_API_BASE_URL_ASR="http://0.0.0.0:10803"
export DWANI_API_BASE_URL_LLM="http://0.0.0.0:10802"
go run .   # listens on :8000
```

Optional: `PORT=8001 HOST=0.0.0.0 go run .`

## Docker

```bash
cp .env.example .env
# Edit .env with your TTS/ASR/LLM URLs
docker compose up -d
```

App is available on **http://localhost:80**.

## Test

```bash
curl -X POST 'http://localhost:8000/v1/speech_to_speech?language=kannada' \
  -F 'file=@kannada_sample.wav' -o out.mp3
```
