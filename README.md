# ExpoMind - real-data Docker application

ExpoMind runs as three Docker services: Nginx/PWA frontend, FastAPI backend and PostgreSQL 16 database. The application does not generate contacts, scores, conversations, tasks or graph nodes. All business information shown after login comes from the authenticated user's PostgreSQL records.

## Start

```powershell
Copy-Item .env.example .env
# Edit .env and replace every password and secret.
docker compose up --build -d
```

Open `http://localhost:8088` (or the `APP_PORT` value from `.env`).

## Real Qwen integration

Set `DASHSCOPE_API_KEY` in `.env` to enable the real AI actions. The backend calls the OpenAI-compatible DashScope endpoint using `QWEN_VISION_MODEL` for business-card extraction and `QWEN_TEXT_MODEL` for transcript analysis. When the key is absent or the provider fails, the UI shows the error and no fallback data is created.

- **Scan card** captures the current camera frame or accepts a phone camera/file upload.
- Extracted fields are placed in a review form and are not stored until a user confirms them.
- **Analyze real transcript** produces a summary, interests, qualification score, next action and supporting excerpts.
- Saving updates the selected contact and stores the conversation in PostgreSQL.

## Administrator

The backend creates or promotes the account defined by `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `ADMIN_NAME` at startup. Change these values before the first deployment. An administrator sees **User Admin**, where they can:

- view registered users and their contact counts;
- enable or disable accounts;
- grant or remove administrator access.

Ordinary JWTs cannot call `/admin/*`. Disabled accounts are rejected immediately, including requests made with an earlier token.

## Real data flow

1. Registering creates only a user account and an empty workspace.
2. Create a contact using details confirmed by the person or copied from their card.
3. Select that database contact before starting a conversation.
4. With explicit consent, start the camera and microphone.
5. The browser transcribes actual microphone audio where Web Speech API is supported.
6. Saving writes the actual transcript and entered next action to PostgreSQL.
7. Contacts, metrics, graph nodes and follow-up cards are rebuilt from API data.

The system never treats face detection as identity recognition. A detected face is labelled identity unknown until the operator selects a verified database contact.

## Face tracking

The camera overlay follows the largest detected face on every processed video frame. It uses the browser FaceDetector API when available and MediaPipe Face Detector as a fallback. The MediaPipe fallback currently downloads its WebAssembly runtime and model from official/public CDN storage; for an offline production deployment, vendor these assets into the frontend image.

Camera and microphone access require HTTPS on a phone or any host other than `localhost`.

## Production HTTPS

Point your domain DNS record to the Docker host, set `DOMAIN` in `.env`, allow inbound ports 80 and 443, then run:

```powershell
docker compose --profile production up --build -d
```

The optional Caddy container obtains and renews TLS certificates automatically and adds security and device-permission headers. The PWA can then use camera and microphone on phones.

## Database migrations and tests

The backend runs `alembic upgrade head` before starting the API. To run the automated security/core tests:

```powershell
docker compose run --rm --no-deps backend pytest -q
```

## Mobile

The frontend is an installable PWA with responsive bottom navigation. Deploy behind HTTPS, open it on the phone, then choose **Add to Home Screen**. For app-store distribution, wrap the same client with Capacitor and add native secure storage, camera, microphone and notification plugins.

## WeChat Mini Program

The native Mini Program client is in `miniprogram/`. It shares this backend and PostgreSQL database and includes WeChat login, contacts, consent-gated camera capture, real Qwen card extraction and transcript analysis, follow-ups and administrator controls. See `miniprogram/README.md` for AppID, server-domain and release configuration.

Set these server-only values before using WeChat login:

```env
WECHAT_APP_ID=your-app-id
WECHAT_APP_SECRET=your-app-secret
```

Never put the AppSecret in Mini Program source code.

## Security notes

- Passwords use Argon2 hashing.
- Protected APIs require expiring JWTs.
- Contact and conversation queries are scoped to the authenticated user.
- Only port 8080 is exposed; backend and PostgreSQL remain internal.
- Use a reverse proxy with TLS, rotate secrets, add rate limiting and replace startup schema updates with Alembic before production.
