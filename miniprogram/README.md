# ExpoMind WeChat Mini Program

This directory is a native WeChat Mini Program client for the existing ExpoMind API and PostgreSQL database.

## Configure

1. Register a Mini Program in the WeChat public platform.
2. Replace `touristappid` in `project.config.json` with the real AppID.
3. Set `WECHAT_APP_ID` and `WECHAT_APP_SECRET` in the server `.env` file. Never put the AppSecret in this client.
4. Set the deployed HTTPS API URL in `config.js`.
5. Add that HTTPS domain to **Development > Development Management > Server Domain** as a request and uploadFile domain.
6. Import this `miniprogram` directory in WeChat DevTools.

## Local Docker development

The development environment defaults to the current development computer's LAN endpoint, matching the root Docker Compose stack. `project.config.json` disables request-domain validation for local DevTools only. A physical phone cannot use `127.0.0.1` because that address points back to the phone itself.

1. Start the root stack with `docker compose up --build -d`.
2. Import this directory into WeChat DevTools using the test AppID, or replace `touristappid` with your AppID.
3. When `WECHAT_APP_ID` and `WECHAT_APP_SECRET` are empty, use the development-only email/password form on the login page.
4. For trial and release builds, replace the `trial` and `release` endpoints in `config.js` with your registered HTTPS domain and re-enable `urlCheck` before submission.

For real-device debugging, connect the phone and computer to the same Wi-Fi. On the login page, enter `http://<computer-LAN-IP>:8088/api`, then tap **测试并保存接口**. If the computer's DHCP address changes, update it there without rebuilding the Mini Program.

You can temporarily override the API endpoint from the DevTools console:

```javascript
wx.setStorageSync('apiBaseUrl', 'https://your-domain.example/api')
```

## Real workflow

- `wx.login` sends a one-time code to `/api/auth/wechat`.
- The backend exchanges it through WeChat `jscode2session` and stores only the resulting OpenID mapping.
- Contacts, conversations, tasks and admin data use the same protected APIs as the web PWA.
- A card photo is uploaded to the real Qwen-VL endpoint. Extracted fields must be reviewed before saving.
- Transcript analysis calls the real Qwen text model. Without an API key, the backend returns an explicit unavailable error.
- With explicit consent, the capture page can record up to 60 seconds of MP3 audio, upload it to the local Whisper endpoint and append the real transcription to the conversation draft.
- Contact creation and editing includes phone, email, summary, gender, interests and qualification score.

## Before review and release

- Complete the Mini Program privacy-protection guidelines for camera and any future microphone use.
- Provide a privacy policy and user-data deletion path.
- Ensure capture is impossible until the operator confirms the other person's consent.
- Use an ICP-compliant HTTPS domain where required.
- Test on physical iOS and Android devices; camera behavior cannot be fully validated in the simulator.
- Replace English fallback error messages with final localized product copy if desired.

The Mini Program does not perform biometric identity recognition. Camera capture and database contact selection are separate, explicit actions.
