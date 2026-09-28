# clients/web — module map
#
# Entry: `app.js` (ES module) + `pixel-bot.js` (IIFE atlas player).
#
# | Module | Responsibility |
# |--------|----------------|
# | `js/dom.js` | `$` helper |
# | `js/protocol.js` | Device Protocol envelope |
# | `js/prefs.js` | localStorage connection + device id |
# | `js/text.js` | normalizeReply / renderMarkdown / process clip |
# | `js/wav.js` | PCM → WAV + resample |
# | `js/store.js` | shared mutable state + UI hooks |
# | `js/pets.js` | PixelBot instances |
# | `js/recorder.js` | mic open / release / take WAV |
# | `js/tts.js` | TTS queue + playback |
# | `js/mood.js` | mood transitions + control sync |
# | `js/transcript.js` | bubbles, process line, attachments |
# | `js/session.js` | WS connect, turn events, talk/send |
# | `js/chrome.js` | settings / sidebar / composer wiring |
#
# Serve with `python serve.py` or `python clients/cli/main.py --ui`.
