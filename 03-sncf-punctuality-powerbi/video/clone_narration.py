"""Read a narration script aloud in a cloned voice, scene by scene (Coqui XTTS-v2, runs locally on CPU).

Usage (use the isolated environment that has coqui-tts installed):
    python clone_narration.py narration.json OUT_DIR REF1.wav [REF2.wav ...] [--lang en]

- narration.json : list of {"id", "caption", "text"} (see narration.json in this folder)
- REF*.wav       : clean recordings of the speaker, 6 to 30 seconds in total is enough, more is better
- OUT_DIR        : one WAV per scene is written as OUT_DIR/<id>.wav

The model licence (Coqui Public Model License) allows non-commercial use only.
Nothing is uploaded: the model and the voice samples stay on this machine.
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")  # the user accepted the non-commercial licence

from TTS.api import TTS  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    lang = "en"
    if "--lang" in sys.argv:
        lang = sys.argv[sys.argv.index("--lang") + 1]
        args = [a for a in args if a != lang]
    script, out_dir, refs = Path(args[0]), Path(args[1]), args[2:]
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes = json.loads(script.read_text(encoding="utf-8"))
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
    for sc in scenes:
        t0 = time.time()
        target = out_dir / f"{sc['id']}.wav"
        tts.tts_to_file(text=sc["text"], speaker_wav=refs, language=lang, file_path=str(target))
        print(f"{sc['id']}: {target.stat().st_size / 1e6:.1f} MB in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
