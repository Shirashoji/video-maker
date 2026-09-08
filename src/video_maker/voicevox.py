import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

from .models import Voice


class Voicevox:
    def __init__(self):
        self.url = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021").rstrip("/")

    def request(self, endpoint, params=None, body=None, method="GET"):
        url = self.url + endpoint
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                return response.read()
        except Exception as e:
            raise RuntimeError(f"VOICEVOX at {self.url}: {e}. Start VOICEVOX first.") from e

    def speakers(self):
        return json.loads(self.request("/speakers"))

    def synthesize(self, voice: Voice, cache: Path) -> Path:
        # Include engine version and endpoint so model/engine changes do not reuse stale audio.
        version = self.request("/version").decode()
        key = hashlib.sha256((self.url + version + voice.model_dump_json()).encode()).hexdigest()
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / f"voice-{key}.wav"
        if path.exists():
            return path
        query = json.loads(self.request("/audio_query", {"text": voice.text, "speaker": voice.speaker}, method="POST"))
        query.update(speedScale=voice.speed, pitchScale=voice.pitch, volumeScale=voice.volume,
                     outputSamplingRate=48000, outputStereo=False)
        wav = self.request("/synthesis", {"speaker": voice.speaker}, query, "POST")
        if not wav.startswith(b"RIFF"):
            raise RuntimeError("VOICEVOX returned invalid WAV")
        # Concurrent identical synthesis may race safely: each writes its own file then replaces.
        import tempfile
        with tempfile.NamedTemporaryFile(dir=cache, suffix=".wav", delete=False) as f:
            f.write(wav)
            tmp = Path(f.name)
        tmp.replace(path)
        path.with_suffix(".json").write_text(json.dumps(query, ensure_ascii=False, indent=2))
        return path
