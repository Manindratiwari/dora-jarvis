# Dora — repaired standalone AI voice assistant

This version repairs the chat/voice flow and adds optional neural text-to-speech. The UI keeps the original Dora design.

## What was fixed

- Replaced the very small default request limit with a configurable 60 requests/minute limit and clearer retry messages.
- Added useful server-side error messages for invalid API keys, unsupported model IDs, provider rate limits and timeouts.
- Added `/api/speech` for natural neural speech. The default voice is `coral`; the frontend automatically falls back to the browser's installed voice if neural TTS is not configured or unavailable.
- Improved female-voice preference in browser fallback and fixed wake-word listening restart after Dora finishes speaking.
- Added health diagnostics that show whether chat and neural voice are configured without exposing secrets.
- Kept API keys on the server; no key is placed in browser JavaScript.

## Required setup

Dora needs an LLM API key to answer questions. A Claude.ai subscription/free message allowance is **not** an Anthropic API key.

For the most natural female voice, also add an OpenAI API key for text-to-speech. This is a separate API service and may incur usage charges. If you do not add it, Dora falls back to the voice installed in Chrome/Edge, whose quality depends on the device.

## Deploy on Render

1. Extract this ZIP and upload the `dora` folder to a GitHub repository.
2. In Render, create a **New Web Service** and connect that repository.
3. Render can use the included `render.yaml`, or enter:
   - Build command: `pip install -r backend/requirements.txt`
   - Start command: `uvicorn --app-dir backend main:app --host 0.0.0.0 --port $PORT`
4. Add these Environment Variables in Render:
   - `LLM_PROVIDER` = `anthropic` (or `openai`)
   - `LLM_MODEL` = a model ID enabled for your provider account (default in this project: `claude-sonnet-4-5`)
   - `LLM_API_KEY` = your provider API key
   - `OPENAI_API_KEY` = your OpenAI API key (needed for natural neural voice)
   - `TTS_MODEL` = `gpt-4o-mini-tts`
   - `TTS_VOICE` = `coral`
   - `RATE_LIMIT_PER_MIN` = `60`
5. Deploy. Open your service's HTTPS URL in Chrome or Edge and allow microphone access.
6. Open `https://YOUR-SERVICE-URL/api/health`. For full functionality it should report `chat_configured: true` and `neural_voice_configured: true`.

If you choose `LLM_PROVIDER=openai`, set `LLM_MODEL` to a chat model available to your OpenAI API project and use `LLM_API_KEY` as that OpenAI key. `OPENAI_API_KEY` can use the same key for speech.

## Run locally (Windows)

```powershell
cd dora\backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
# Edit backend\.env and add your API keys. Keep the file private.
uvicorn main:app --reload --port 8010
```

Open `http://localhost:8010` in Chrome/Edge. Microphone access requires localhost or HTTPS.

## Voice notes

- Neural voice is generated server-side with the configured TTS provider. It sounds more natural than browser speech synthesis, but quality and availability depend on provider access and billing.
- If the neural voice request fails, browser speech synthesis is used as a fallback.
- Voice input uses the browser Web Speech API. Chrome/Edge desktop generally work best; support varies by browser/device and recognition may require internet access.
- “Hey Dora” only listens while the Dora tab is open and active. Browsers do not allow reliable always-on background wake-word listening.
- The app does not yet include reminders, web search, persistent server-side conversation storage, or native mobile wake-word support.
