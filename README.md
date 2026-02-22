Talk - dwani.ai

talk.dwani.ai / dwani.ai



export DWANI_API_BASE_URL_TTS="http://0.0.0.0:10804"

export DWANI_API_BASE_URL_ASR="http://0.0.0.0:10803"

export DWANI_API_BASE_URL_LLM="asd"

python3.10 -m venv venv
source venv/bin/activate
python main.py


 curl -X 'POST'   'http://localhost:8001/v1/speech_to_speech?language=kannada'   -H 'accept: application/json'   -H 'Content-Type: multipart/form-data'   -F 'file=@kannada_sample.wav;type=audio/x-wav' -o test.mp3

 Check test.mp3

