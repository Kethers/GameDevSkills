"""
Reusable talk/presentation video downloader (portable) — YouTube + Bilibili.

- Auto-detects the platform from the URL and picks the matching cookie file
  (www.youtube.com_cookies.txt / www.bilibili.com_cookies.txt) from the CWD.
- YouTube: handles the JS 'n challenge' via a Node.js runtime + yt-dlp-ejs.
- Bilibili: skips the Node runtime; uses ai-zh/zh subtitle langs by default. NOTE that
  yt-dlp frequently misses Bilibili AI subtitles — use scripts/bili_subs.py as fallback.
- Downloads >=1080p MP4 (H.264 preferred for player compatibility) merged with best audio,
  and fetches available subtitles as .srt.

Run with the Python interpreter that has yt-dlp[default] + imageio-ffmpeg installed
(e.g. the managed venv's python.exe). Node >=22 auto-detected (YouTube only), or pass --node.

Usage:
  python yt_download.py <url> <output_dir> <basename> \
      [--subs <langs>] [--cookies path] [--node path] [--ffmpeg-dir path]
  # --subs empty -> auto: YouTube "en,en-orig,zh-Hans,zh-Hant"; Bilibili "ai-zh,zh-Hans,zh-CN,zh-Hant"

Path handling: yt-dlp is a Windows process; a Git-Bash path like /d/foo would land in
D:/d/foo. This script normalizes /x/... to X:/ style automatically. Prefer calling it from a
Python subprocess with raw strings to avoid shell quoting issues with apostrophes in titles.
"""
import sys, os, subprocess, argparse, glob

def find_node(explicit=None):
    if explicit and os.path.exists(explicit):
        return explicit
    # 1) managed node under ~/.workbuddy/binaries/node/versions/*/node.exe
    home = os.path.expanduser("~")
    pats = [
        os.path.join(home, ".workbuddy", "binaries", "node", "versions", "*", "node.exe"),
        os.path.join(home, ".workbuddy", "binaries", "node", "versions", "*", "bin", "node"),
    ]
    cands = []
    for p in pats:
        cands += glob.glob(p)
    if cands:
        cands.sort(reverse=True)  # newest version first
        return cands[0]
    # 2) node on PATH
    from shutil import which
    n = which("node")
    return n  # may be None -> yt-dlp will error clearly

def find_ffmpeg_dir(explicit=None):
    if explicit and os.path.isdir(explicit):
        return explicit
    home = os.path.expanduser("~")
    p = os.path.join(home, ".workbuddy", "binaries", "ffmpeg", "bin")
    if os.path.exists(os.path.join(p, "ffmpeg.exe")) or os.path.exists(os.path.join(p, "ffmpeg")):
        return p
    # fall back to imageio-ffmpeg static build; copy into a stable ffmpeg.exe dir
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        os.makedirs(p, exist_ok=True)
        import shutil
        dst = os.path.join(p, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if not os.path.exists(dst):
            shutil.copy(ff, dst)
        return p
    except Exception:
        return None

def norm_path(pth):
    if os.name == "nt" and pth.startswith("/") and len(pth) > 2 and pth[2] == "/":
        pth = pth[1].upper() + ":" + pth[2:].replace("/", "\\")
    return os.path.abspath(pth)

def detect_platform(url):
    u = url.lower()
    if "bilibili.com" in u or u.startswith("bv") or "b23.tv" in u:
        return "bilibili"
    return "youtube"

def auto_cookies(url, explicit):
    if explicit:
        return explicit
    # look for a platform cookie file in CWD / workspace
    plat = detect_platform(url)
    names = (["www.bilibili.com_cookies.txt", "bilibili.com_cookies.txt"] if plat == "bilibili"
             else ["www.youtube.com_cookies.txt", "youtube.com_cookies.txt"])
    for n in names:
        if os.path.exists(n):
            return os.path.abspath(n)
    return ""

def run(url, outdir, base, sub_langs, cookies, node, ffmpeg_dir, hls=False, no_subs=False):
    outdir = norm_path(outdir)
    os.makedirs(outdir, exist_ok=True)
    plat = detect_platform(url)
    cookies = auto_cookies(url, cookies)
    ffdir = find_ffmpeg_dir(ffmpeg_dir)
    outtmpl = os.path.join(outdir, base + ".%(ext)s")
    cmd = [sys.executable, "-m", "yt_dlp"]
    if cookies and os.path.exists(cookies):
        cmd += ["--cookies", cookies]
    # The JS n-challenge / Node runtime is a YouTube-only concern.
    if plat == "youtube":
        node = find_node(node)
        if node:
            cmd += ["--js-runtimes", f"node:{node}"]
    if ffdir:
        cmd += ["--ffmpeg-location", ffdir]

    if plat == "youtube" and hls:
        # HLS mode: modern Unreal Fest / many YouTube videos only expose 1080p via HLS
        # (DASH formats 299/137 are PO-token-gated -> "Requested format not available"
        # or only 360p fmt 18). The web_safari/web clients expose formats 300 (720p) /
        # 301 (1080p) as m3u8 only. Use ffmpeg as the HLS downloader so it STREAMS the
        # m3u8 into a single mp4 (native HLS writes 300+ .part-FragN temp files and
        # deletes each after merge, which trips the sandbox bulk-delete guard).
        # 301-21 is typically the en-US ORIGINAL audio variant; 301 falls back to any.
        cmd += ["--extractor-args", "youtube:player_client=web_safari,web",
                "--downloader", "ffmpeg", "--hls-prefer-ffmpeg",
                "-f", "301-21/301/300/best[height<=1080]"]
    elif plat == "bilibili":
        # Bilibili is DASH: video and audio are SEPARATE streams (e.g. 30112 = 1080p
        # avc1 video-only, 30280 = m4a 113k audio-only). We MUST download bestvideo +
        # bestaudio and let yt-dlp merge them (--merge-output-format mp4 below). Do NOT
        # put any YouTube format id (299 etc.) here — it doesn't exist on Bilibili.
        cmd += ["-f", "bestvideo[height<=1080]+bestaudio/bestvideo+bestaudio/best"]
    else:
        # YouTube DASH-first: prefer H.264 1080p (fmt 299) + m4a -> mp4; fall back to <=1080p.
        cmd += ["-f", ("299+bestaudio[ext=m4a]/bestvideo[height<=1080][vcodec^=avc1]+bestaudio/"
                       "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best")]

    cmd += ["--merge-output-format", "mp4", "--no-playlist"]
    # Subtitles: skip entirely when captions are PO-token-gated (YouTube HLS) and you
    # plan to ASR instead; otherwise fetch available subs as .srt.
    if not no_subs:
        if not sub_langs:
            sub_langs = "ai-zh,zh-Hans,zh-CN,zh-Hant" if plat == "bilibili" else "en,en-orig,zh-Hans,zh-Hant"
        cmd += ["--write-subs", "--write-auto-subs", "--sub-langs", sub_langs, "--convert-subs", "srt"]
    cmd += ["-o", outtmpl, url]

    print("PLATFORM:", plat, "| HLS:", hls, "| no_subs:", no_subs)
    print("COOKIES:", cookies or "(none)")
    print("FFMPEG_DIR:", ffdir)
    print("RUN:", " ".join(f'"{c}"' if " " in c else c for c in cmd))
    rc = subprocess.run(cmd).returncode
    if plat == "bilibili":
        print("\nNOTE: Bilibili AI subtitles are often missed by yt-dlp. If no .srt was\n"
              "produced, run scripts/bili_subs.py to fetch the ai-zh subtitle directly.")
    return rc

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("outdir")
    ap.add_argument("base")
    ap.add_argument("--subs", default="")  # empty -> auto per platform
    ap.add_argument("--cookies", default=os.environ.get("YT_COOKIES", ""))
    ap.add_argument("--node", default=os.environ.get("YT_NODE", ""))
    ap.add_argument("--ffmpeg-dir", default=os.environ.get("YT_FFMPEG_DIR", ""))
    ap.add_argument("--hls", action="store_true",
                    help="YouTube only: use web_safari client + ffmpeg HLS downloader for 1080p "
                         "(when DASH is PO-token-gated / only 360p shows). Avoids per-fragment temp files.")
    ap.add_argument("--no-subs", action="store_true",
                    help="Skip subtitle download (use when captions are PO-token-blocked and you will ASR).")
    a = ap.parse_args()
    sys.exit(run(a.url, a.outdir, a.base, a.subs, a.cookies, a.node, a.ffmpeg_dir, a.hls, a.no_subs))
