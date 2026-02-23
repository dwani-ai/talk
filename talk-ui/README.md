# Talk UI

Simple push-to-talk React app for the Talk (speech-to-speech) backend.

- **Hold** the button to record, **release** to send. The backend returns an MP3 reply and it plays automatically.
- Choose **language**: Kannada, Hindi, or Tamil.

## Setup

```bash
npm install
```

## Run (dev)

Backend must be running (e.g. `python main.py --port 8001`). The dev server proxies `/v1` to `http://localhost:8001`.

```bash
npm run dev
```

Open http://localhost:5173

## Backend URL

- **Dev**: Uses Vite proxy: requests to `/v1/*` go to `http://localhost:8001`. No env needed if the backend is on 8001.
- **Production**: Set `VITE_API_URL` to your API origin (e.g. `https://talk.example.com`) before building:

  ```bash
  VITE_API_URL=https://talk.example.com npm run build
  ```

Then serve the `dist/` folder (e.g. `npm run preview` or any static host).

## Build

```bash
npm run build
```

Output is in `dist/`.
