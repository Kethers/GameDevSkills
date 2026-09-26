"""
One-time environment setup for the youtube-video-to-notes skill.

Creates (or reuses) an isolated Python venv and installs all dependencies:
  yt-dlp[default] (bundles yt-dlp-ejs for the YouTube JS n-challenge),
  imageio-ffmpeg (static ffmpeg), opencv-python-headless, numpy, httpx (Bilibili API),
  faster-whisper (local ASR fallback for PO-token-blocked / caption-less videos).
Also materializes a stable ffmpeg.exe under ~/.workbuddy/binaries/ffmpeg/bin.

Run with ANY available python (managed preferred):
  python setup_env.py [--venv <dir>]

Prints the venv python path to use for all subsequent script calls.
"""
import sys, os, subprocess, argparse, glob

def managed_python():
    home = os.path.expanduser("~")
    pats = [os.path.join(home, ".workbuddy", "binaries", "python", "versions", "*", "python.exe"),
            os.path.join(home, ".workbuddy", "binaries", "python", "versions", "*", "bin", "python")]
    c = []
    for p in pats: c += glob.glob(p)
    c.sort(reverse=True)
    return c[0] if c else sys.executable

def main():
    home = os.path.expanduser("~")
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv", default=os.path.join(home, ".workbuddy", "binaries", "python", "envs", "yt2notes"))
    a = ap.parse_args()
    base_py = managed_python()
    venv = a.venv
    if not os.path.exists(venv):
        print(f"[setup] creating venv at {venv} using {base_py}")
        subprocess.run([base_py, "-m", "venv", venv], check=True)
    vpy = os.path.join(venv, "Scripts", "python.exe")
    if not os.path.exists(vpy):
        vpy = os.path.join(venv, "bin", "python")
    print("[setup] installing deps ...")
    subprocess.run([vpy, "-m", "pip", "install", "-q", "-U",
                    "yt-dlp[default]", "imageio-ffmpeg",
                    "opencv-python-headless", "numpy", "httpx", "faster-whisper"], check=True)
    # materialize stable ffmpeg.exe
    ffbin = os.path.join(home, ".workbuddy", "binaries", "ffmpeg", "bin")
    os.makedirs(ffbin, exist_ok=True)
    dst = os.path.join(ffbin, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not os.path.exists(dst):
        code = ("import imageio_ffmpeg,shutil,os;"
                f"shutil.copy(imageio_ffmpeg.get_ffmpeg_exe(), r'{dst}')")
        subprocess.run([vpy, "-c", code], check=True)
    print("\n[setup] DONE")
    print("VENV_PYTHON=" + vpy)
    print("FFMPEG=" + dst)

if __name__ == "__main__":
    main()
