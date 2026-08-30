# Browser support

DoGoods targets **modern browsers** — the last two major versions of Chrome, Firefox, Safari (macOS), Edge, and Safari on iOS 15+.

Internet Explorer and other pre-ES2020 engines are **not supported**. The app uses ES modules, React 18, and Mapbox GL v2.

## Supported browsers

| Browser | Minimum |
|---|---|
| Google Chrome | Last 2 major versions |
| Microsoft Edge | Last 2 major versions |
| Mozilla Firefox | Last 2 major versions |
| Safari (macOS) | Last 2 major versions |
| Safari (iOS) | iOS 15+ |

Build tooling uses the `browserslist` field in [`package.json`](../package.json) so Autoprefixer and Vite align CSS/JS output with this matrix.

## Feature compatibility

| Feature | Chrome / Edge | Firefox | Safari (desktop) | iOS Safari |
|---|---|---|---|---|
| Core forms and auth | Yes | Yes | Yes | Yes |
| Map (Mapbox) | Yes | Yes | Yes | Yes |
| Chat voice upload (Whisper) | Yes | Yes | Yes | Yes (`audio/mp4` when webm unavailable) |
| Browser speech-to-text (Web Speech API) | Yes | Limited | Yes (`webkitSpeechRecognition`) | Yes |
| Form text hints (Nouri guide bar) | Yes | Yes | Yes | Yes |
| Form voice guide (opt-in TTS) | Yes | Yes | Yes | Yes (may require user gesture) |
| AI TTS autoplay | Yes | Yes | Tap-to-hear fallback | Tap-to-hear fallback |

### Graceful degradation

- **Voice location search / chat mic**: Uses [`utils/mediaRecorder.js`](../utils/mediaRecorder.js) to pick a Safari-safe recording format. Unsupported browsers show a clear error instead of failing silently.
- **Maps**: If Mapbox CDN is blocked or unavailable, [`FoodMap`](../components/common/FoodMap.jsx) shows a list-view hint instead of a blank map.
- **Form voice**: Off by default; enable **Form voice guide** under Settings → Accessibility.

## Automated checks

- **Jest**: unit tests including MediaRecorder mime selection
- **Playwright**: smoke tests on `/login`, `/signup`, `/how-it-works`, `/find-food` across Chromium, Firefox, and WebKit (CI)

Run locally:

```bash
npm run build
npm run test:browsers
```

## Reporting issues

If something breaks in a supported browser, include the browser name, version, OS, and steps to reproduce in your bug report.
