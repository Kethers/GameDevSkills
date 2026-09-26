"""
Local ASR fallback for talks whose captions are PO-token-blocked (YouTube) or absent.

Extracts 16kHz mono audio from the video with ffmpeg, then transcribes with
faster-whisper (CTranslate2, CPU-friendly, no PyTorch). Writes an SRT + a plain
transcript. The SRT is then fed through clean_auto_srt.py -> build_subs.py exactly
like a raw auto-caption track.

Requires: faster-whisper (pip install faster-whisper) + ffmpeg (auto-detected).
Rough speed: the "small.en" model does a ~40-min talk in ~10-15 min on CPU
(plus a one-time model download on first use).

Usage:
  python asr_transcribe.py "<video.mp4>" "<out_dir>" [--model small.en] [--lang en]
    -> writes <out_dir>/asr.<lang>.srt  and  <out_dir>/asr.<lang>.txt

Tip: after running, fix obvious ASR mishears using the slides / title card
(e.g. a solver/product/person name), since Whisper guesses proper nouns.
"""
import sys, os, argparse, subprocess, glob


def find_ffmpeg():
    home = os.path.expanduser("~")
    p = os.path.join(home, ".workbuddy", "binaries", "ffmpeg", "bin",
                     "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if os.path.exists(p):
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace('.', ',')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out_dir")
    ap.add_argument("--model", default="small.en",
                    help="faster-whisper model: small.en (default, good speed/quality on CPU), "
                         "base.en (faster), medium.en / large-v3 (slower, better). Use non-.en model for non-English.")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--compute", default="int8", help="int8 (default, CPU) / int8_float16 / float16 (GPU)")
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args()

    os.makedirs(a.out_dir, exist_ok=True)
    wav = os.path.join(a.out_dir, "audio.wav")
    ff = find_ffmpeg()
    # 16kHz mono is what Whisper wants; keeps the wav small-ish.
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", a.video, "-ac", "1", "-ar", "16000", wav], check=True)
    print("wav:", os.path.getsize(wav) // 1024 // 1024, "MB")

    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device=a.device, compute_type=a.compute)
    segments, info = model.transcribe(
        wav, language=(None if a.lang in ("", "auto") else a.lang),
        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500), beam_size=5)

    lang = a.lang if a.lang not in ("", "auto") else (info.language or "en")
    srt = os.path.join(a.out_dir, f"asr.{lang}.srt")
    txt = os.path.join(a.out_dir, f"asr.{lang}.txt")
    segs = list(segments)
    with open(srt, "w", encoding="utf-8") as f:
        for i, s in enumerate(segs, 1):
            f.write(f"{i}\n{ts(s.start)} --> {ts(s.end)}\n{s.text.strip()}\n\n")
    with open(txt, "w", encoding="utf-8") as f:
        for s in segs:
            f.write(s.text.strip() + "\n")
    print(f"segments: {len(segs)} | duration: {round(info.duration/60,1)} min")
    print("SRT:", srt)
    print("TXT:", txt)


if __name__ == "__main__":
    main()
