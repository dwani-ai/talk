package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"os"
	"strings"
	"time"
)

const (
	defaultPort = "8000"
	defaultHost = "0.0.0.0"
)

var (
	allowedLanguages = map[string]bool{"kannada": true, "hindi": true, "tamil": true}
)

func main() {
	for _, name := range []string{"DWANI_API_BASE_URL_LLM", "DWANI_API_BASE_URL_TTS", "DWANI_API_BASE_URL_ASR"} {
		if os.Getenv(name) == "" {
			log.Fatalf("environment variable %s must be set", name)
		}
	}
	port := os.Getenv("PORT")
	if port == "" {
		port = defaultPort
	}
	host := os.Getenv("HOST")
	if host == "" {
		host = defaultHost
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/v1/speech_to_speech", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost && r.Method != http.MethodOptions {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if r.Method == http.MethodOptions {
			cors(ok)(w, r)
			return
		}
		cors(speechToSpeech)(w, r)
	})
	log.Printf("Listening on %s:%s", host, port)
	if err := http.ListenAndServe(host+":"+port, mux); err != nil {
		log.Fatal(err)
	}
}

func cors(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "*")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}
		next(w, r)
	}
}

func ok(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) }

func speechToSpeech(w http.ResponseWriter, r *http.Request) {
	language := r.URL.Query().Get("language")
	if language == "" || !allowedLanguages[language] {
		writeJSONError(w, http.StatusBadRequest, "language must be one of [kannada, hindi, tamil]")
		return
	}
	file, _, err := r.FormFile("file")
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "missing or invalid file")
		return
	}
	defer file.Close()

	// 1. ASR
	asrText, err := transcribe(file, language)
	if err != nil {
		log.Printf("ASR error: %v", err)
		writeJSONError(w, http.StatusInternalServerError, err.Error())
		return
	}
	asrText = strings.TrimSpace(asrText)
	if asrText == "" {
		writeJSONError(w, http.StatusBadRequest, "no speech detected in the audio")
		return
	}

	// 2. LLM
	llmText, err := callLLM(asrText)
	if err != nil {
		log.Printf("LLM error: %v", err)
		writeJSONError(w, http.StatusBadGateway, err.Error())
		return
	}
	llmText = strings.TrimSpace(llmText)
	if llmText == "" {
		writeJSONError(w, http.StatusBadGateway, "LLM returned empty text for TTS")
		return
	}
	llmText = strings.Join(strings.Fields(llmText), " ") // single line

	// 3. TTS
	audio, err := callTTS(llmText)
	if err != nil {
		log.Printf("TTS error: %v", err)
		writeJSONError(w, http.StatusBadGateway, err.Error())
		return
	}
	if len(audio) == 0 {
		writeJSONError(w, http.StatusBadGateway, "TTS returned empty audio")
		return
	}

	w.Header().Set("Content-Type", "audio/mp3")
	w.Header().Set("Content-Disposition", `inline; filename="speech.mp3"`)
	w.Header().Set("Cache-Control", "no-cache")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(audio)
}

func transcribe(file io.Reader, language string) (string, error) {
	base := strings.TrimSuffix(os.Getenv("DWANI_API_BASE_URL_ASR"), "/")
	url := base + "/transcribe/?language=" + language
	data, err := io.ReadAll(file)
	if err != nil {
		return "", fmt.Errorf("reading upload: %w", err)
	}
	reqBody := &bytes.Buffer{}
	writer := multipart.NewWriter(reqBody)
	part, _ := writer.CreateFormFile("file", "audio.wav")
	_, _ = part.Write(data)
	_ = writer.Close()
	req, _ := http.NewRequest(http.MethodPost, url, reqBody)
	req.Header.Set("Accept", "application/json")
	req.Header.Set("Content-Type", writer.FormDataContentType())
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("ASR request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("ASR %d: %s", resp.StatusCode, string(b))
	}
	var out struct {
		Text string `json:"text"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", fmt.Errorf("ASR response: %w", err)
	}
	return out.Text, nil
}

func callLLM(userText string) (string, error) {
	base := strings.TrimSuffix(os.Getenv("DWANI_API_BASE_URL_LLM"), "/")
	if !strings.HasSuffix(base, "/v1") {
		base = base + "/v1"
	}
	url := base + "/chat/completions"
	model := os.Getenv("DWANI_LLM_MODEL")
	if model == "" {
		model = "gemma3"
	}
	reqBody := map[string]any{
		"model": model,
		"messages": []map[string]string{
			{"role": "system", "content": "You must respond in at most one line. Keep your reply to a single short sentence."},
			{"role": "user", "content": userText},
		},
		"max_tokens": 256,
	}
	body, _ := json.Marshal(reqBody)
	req, _ := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer dummy")
	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("LLM request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("LLM %d: %s", resp.StatusCode, string(b))
	}
	var out struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", fmt.Errorf("LLM response: %w", err)
	}
	if len(out.Choices) == 0 {
		return "", fmt.Errorf("LLM returned empty response")
	}
	return out.Choices[0].Message.Content, nil
}

func callTTS(text string) ([]byte, error) {
	base := strings.TrimSuffix(os.Getenv("DWANI_API_BASE_URL_TTS"), "/")
	url := base + "/v1/audio/speech"
	body, _ := json.Marshal(map[string]string{"text": text})
	req, _ := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "*/*")
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("TTS request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("TTS %d: %s", resp.StatusCode, string(b))
	}
	return io.ReadAll(resp.Body)
}

func writeJSONError(w http.ResponseWriter, code int, detail string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{"detail": detail})
}
