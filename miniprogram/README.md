# ExpoMind WeChat Mini Program

This directory is a native WeChat Mini Program client for the existing ExpoMind API and PostgreSQL database.

## Configure

1. Register a Mini Program in the WeChat public platform.
2. Replace `touristappid` in `project.config.json` with the real AppID.
3. Set `WECHAT_APP_ID` and `WECHAT_APP_SECRET` in the server `.env` file. Never put the AppSecret in this client.
4. Set the deployed HTTPS API URL in `config.js`.
5. Add that HTTPS domain to **Development > Development Management > Server Domain** as a request and uploadFile domain.
6. Import this `miniprogram` directory in WeChat DevTools.

## Real workflow

- `wx.login` sends a one-time code to `/api/auth/wechat`.
- The backend exchanges it through WeChat `jscode2session` and stores only the resulting OpenID mapping.
- Contacts, conversations, tasks and admin data use the same protected APIs as the web PWA.
- A card photo is uploaded to the real Qwen-VL endpoint. Extracted fields must be reviewed before saving.
- Transcript analysis calls the real Qwen text model. Without an API key, the backend returns an explicit unavailable error.

## Before review and release

- Complete the Mini Program privacy-protection guidelines for camera and any future microphone use.
- Provide a privacy policy and user-data deletion path.
- Ensure capture is impossible until the operator confirms the other person's consent.
- Use an ICP-compliant HTTPS domain where required.
- Test on physical iOS and Android devices; camera behavior cannot be fully validated in the simulator.
- Replace English fallback error messages with final localized product copy if desired.

The Mini Program does not perform biometric identity recognition. Camera capture and database contact selection are separate, explicit actions.
