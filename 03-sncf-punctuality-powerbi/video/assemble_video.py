"""Assemble the final demo video from the recorded clips, the narration clips and the speaker's greeting.

Usage:
    python assemble_video.py RECORDING_DIR NARRATION_DIR NARRATION_JSON GREETING.wav OUT.mp4 FFMPEG.exe
                             [--title "TGV Punctuality | Power BI"] [--subtitle "Name | Data analysis"]

RECORDING_DIR holds c01.mkv ... and timeline.json written by record_powerbi.ps1.
What it does: trims the start of every clip, joins them, adds a caption bar with the scene title and a
footer with the data caveat, places the greeting and each narration clip at its scene start, normalises the
loudness (-16 LUFS) and exports a 1920x1080 H.264 + AAC file (LinkedIn friendly).
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FOOTER = "Data: SNCF open data (ODbL)  |  Route-level figures, not the official SNCF regularity"


def probe(ffmpeg, f):
    o = subprocess.run([ffmpeg, "-hide_banner", "-i", str(f)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", o)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])


def main():
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    opt = {a: sys.argv[sys.argv.index(a) + 1] for a in sys.argv if a in ("--title", "--subtitle")}
    rec, narr, script, greeting, out, ffmpeg = [Path(p) if i < 5 else p for i, p in enumerate(pos[:6])]
    ffmpeg = str(ffmpeg)
    title = opt.get("--title", "TGV Punctuality | Power BI")
    subtitle = opt.get("--subtitle", "Data analysis project")
    tl = json.loads((rec / "timeline.json").read_text(encoding="utf-8-sig"))
    caps = {s["id"]: s["caption"] for s in json.loads(Path(script).read_text(encoding="utf-8"))}

    work = Path(tempfile.mkdtemp(prefix="assemble_"))
    for f in ("segoeui.ttf", "segoeuib.ttf"):
        shutil.copy(Path("C:/Windows/Fonts") / f, work / f)

    # optional "--clip-max c02=8": keep only the first 8 s of that clip (removes a long idle stretch)
    clip_max = {}
    for a in sys.argv:
        if re.fullmatch(r"c\d+=[\d.]+", a):
            k_, v_ = a.split("="); clip_max[k_] = float(v_)
    inputs, vparts, off, cuts = [], [], 0.0, []
    for i, c in enumerate(tl["clips"]):
        f = rec / c["file"]
        head = max(probe(ffmpeg, f) - c["sw_len"], 0.0)  # the clip started recording before the stopwatch did
        use = min(c["sw_len"], clip_max.get(f.stem, c["sw_len"]))
        if use < c["sw_len"]:
            cuts.append((off + use, off + c["sw_len"]))   # in the original (uncut) timeline
        inputs += ["-ss", f"{head:.3f}", "-t", f"{use:.3f}", "-i", str(f)]
        vparts.append(f"[{i}:v]fps=30,setsar=1[v{i}]")
        off += c["sw_len"]
    n = len(tl["clips"])

    def remap(t):  # original timeline -> timeline after the cuts
        for a_, b_ in cuts:
            if t >= b_:
                t -= (b_ - a_)
            elif t > a_:
                t = a_ - sum(y - x for x, y in cuts if y <= a_)
        return t
    for s in tl["scenes"]:
        s["out_start"], s["out_end"] = remap(s["out_start"]), remap(s["out_end"])
    total = remap(off)
    concat = "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[vc]"

    # caption bar (40 px) under the 1920x1040 screen recording
    f = ["[vc]pad=1920:1080:0:0:color=0x0B1F3A[vp]"]
    last = "vp"
    k = 0
    for s in tl["scenes"]:
        (work / f"cap{k}.txt").write_text(caps.get(s["id"], ""), encoding="utf-8")
        f.append(f"[{last}]drawtext=fontfile=segoeuib.ttf:textfile=cap{k}.txt:fontsize=22:fontcolor=white:x=24:y=1040+(40-text_h)/2"
                 f":enable='between(t,{s['out_start']:.2f},{s['out_end']:.2f})'[c{k}]")
        last = f"c{k}"; k += 1
    (work / "footer.txt").write_text(FOOTER, encoding="utf-8")
    f.append(f"[{last}]drawtext=fontfile=segoeui.ttf:textfile=footer.txt:fontsize=16:fontcolor=0xB9C6DA:x=w-text_w-24:y=1040+(40-text_h)/2[vf]")
    last = "vf"
    # title card during the greeting
    (work / "t1.txt").write_text(title, encoding="utf-8")
    (work / "t2.txt").write_text(subtitle, encoding="utf-8")
    t_end = tl["intro_hold"] - 0.2
    f.append(f"[{last}]drawbox=x=0:y=380:w=1920:h=210:color=0x0B1F3A@0.82:t=fill:enable='between(t,0.3,{t_end:.2f})'[b1]")
    f.append(f"[b1]drawtext=fontfile=segoeuib.ttf:textfile=t1.txt:fontsize=64:fontcolor=white:x=(w-text_w)/2:y=420:enable='between(t,0.3,{t_end:.2f})'[b2]")
    f.append(f"[b2]drawtext=fontfile=segoeui.ttf:textfile=t2.txt:fontsize=34:fontcolor=0xB9C6DA:x=(w-text_w)/2:y=515:enable='between(t,0.3,{t_end:.2f})'[b3]")
    f.append(f"[b3]fade=t=in:st=0:d=0.6,fade=t=out:st={total - 1.0:.2f}:d=1.0[vout]")

    # audio: greeting + one narration clip per scene
    a_in = ["-i", str(greeting)]
    aparts = [f"[{n}:a]highpass=f=70,volume=1.0,adelay=500|500[a0]"]
    mix = "[a0]"
    for j, s in enumerate(tl["scenes"], start=1):
        a_in += ["-i", str(Path(narr) / f"{s['id']}.wav")]
        ms = int(round(s["out_start"] * 1000))
        aparts.append(f"[{n + j}:a]highpass=f=70,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=150,alimiter=limit=0.9,adelay={ms}|{ms}[a{j}]")
        mix += f"[a{j}]"
    aparts.append(f"{mix}amix=inputs={len(tl['scenes']) + 1}:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=9,"
                  f"afade=t=in:st=0:d=0.3,afade=t=out:st={total - 1.0:.2f}:d=1.0,atrim=0:{total:.2f}[aout]")

    fc = ";".join(vparts + [concat] + f + aparts)
    (work / "filter.txt").write_text(fc, encoding="utf-8")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs, *a_in, "-/filter_complex", "filter.txt",
           "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{total:.2f}", str(Path(out).resolve())]
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    print(r.stderr[-1500:] if r.returncode else f"ok: {out}  ({total:.1f} s)")
    shutil.rmtree(work, ignore_errors=True)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
