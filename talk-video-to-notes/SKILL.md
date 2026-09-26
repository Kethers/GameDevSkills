---
name: talk-video-to-notes
description: Download a talk/presentation/lecture video from YouTube OR Bilibili (B站) at >=1080p, fetch or translate subtitles, capture PPT/slide screenshots (avoiding speaker shots and preferring fully-built slides), and produce a rich Chinese Markdown study note. Use when the user gives a YouTube or Bilibili video URL/BV id and asks to download it and/or generate notes/字幕/截图 for a tech talk, keynote, conference session, or Chinese 演讲/公开课. Auto-detects platform: YouTube uses a Node runtime for the JS n-challenge; Bilibili uses the login cookie + a dedicated AI-subtitle fetcher. Installs yt-dlp/ffmpeg into an isolated venv and outputs a self-contained folder named after the video title (video.mp4 + .srt subtitles + Img/ screenshots + note.md).
description_zh: 演讲视频转中文笔记
description_en: Talk video to notes
agent_created: true
---

# talk-video-to-notes

Turn a **YouTube or Bilibili** presentation video into a self-contained study package:
`标题.mp4` (>=1080p) + subtitles (`.zh-CN.srt`, plus `.en.srt` / bilingual `.zh-en.srt` for English talks) + `Img/` (1920x1080 slide screenshots) + `标题.md` (Chinese note). Video and note share the exact title as filename so players auto-detect subtitles.

## When to use
- User provides a **YouTube** (`youtube.com` / `youtu.be`) or **Bilibili** (`bilibili.com` / `BV...` / `b23.tv`) video URL and asks to **download** and/or **make notes / 字幕 / 截图**.
- Especially for **talks / keynotes / tech presentations / 公开课 / 演讲** (slides + speaker intercut).
- Trigger phrases: "下载这个视频并生成笔记", "download + notes", "配字幕", "截取PPT截图", "总结这个B站视频".

## Platform differences (READ FIRST)
| | YouTube | Bilibili |
|---|---|---|
| Cookie file | `www.youtube.com_cookies.txt` | `www.bilibili.com_cookies.txt` |
| JS n-challenge / Node runtime | **required** (`--js-runtimes node:...`) | not needed |
| Video language | usually English → translate subs to zh | usually Chinese → keep zh, no translation |
| Subtitles | manual → auto `en` (clean+translate) | AI `ai-zh` via `bili_subs.py` (yt-dlp often misses it) |
| Note & subtitle output | `.en.srt` + `.zh-CN.srt` + `.zh-en.srt` | `.zh-CN.srt` (+ bilingual only if source is non-Chinese) |

## Step 0 — Environment setup (once, portable)
```
python scripts/setup_env.py
```
Creates an isolated venv (`~/.workbuddy/binaries/python/envs/yt2notes`), installs
`yt-dlp[default]` (bundles **yt-dlp-ejs** for YouTube's n-challenge), `imageio-ffmpeg`,
`opencv-python-headless`, `numpy`, `httpx` (for Bilibili API), and materializes
`~/.workbuddy/binaries/ffmpeg/bin/ffmpeg.exe`. It prints `VENV_PYTHON=...` — use that (`<VPY>`)
for all calls. Node >=22 auto-detected (YouTube only). Put the platform cookie file in the workspace.

## Steps
1. **Probe** (title, duration, language, subtitles, max height):
   - YouTube: `<VPY> -m yt_dlp --cookies www.youtube.com_cookies.txt --js-runtimes "node:<node.exe>" --dump-single-json --skip-download <url>`
   - Bilibili: `<VPY> -m yt_dlp --cookies www.bilibili.com_cookies.txt --dump-single-json --skip-download <url>`
   - If YouTube says "Sign in to confirm you're not a bot" / "n challenge failed", see Pitfalls.
2. **Sanitize the title** → folder/base name. Windows-illegal chars `< > : " / \ | ? *` → `-`. Correct obvious auto-caption mishears of the speaker name using the title slide.
3. **Download** >=1080p mp4 + subs (platform auto-detected; cookie auto-picked from CWD):
   `<VPY> scripts/yt_download.py <url> "<OUTDIR native path>" "<BASE>"`
   - `--subs` empty → auto (YouTube `en,en-orig,zh-Hans,zh-Hant`; Bilibili `ai-zh,zh-Hans,zh-CN,zh-Hant`).
   - **Modern YouTube (e.g. all recent Unreal Fest talks) only expose 1080p via HLS** and the default DASH path yields only 360p or "format not available". Add **`--hls`**: it switches to `player_client=web_safari,web` + the ffmpeg HLS downloader + format `301-21/301/300` (301-21 = en-US original audio) and streams into one mp4 with no per-fragment temp files. **`--no-subs`** skips caption download when they're PO-token-blocked (you'll ASR instead). So the typical modern-YouTube call is: `<VPY> scripts/yt_download.py <url> "<OUTDIR>" "<BASE>" --hls --no-subs`. This replaces the old hand-written per-run `_dl.py`.
4. **Subtitles**:
   - **Bilibili (Chinese)**: if yt-dlp produced no `.srt`, fetch AI subtitle directly:
     `<VPY> scripts/bili_subs.py <bvid_or_url> "<OUTDIR>/<BASE>.zh-CN.srt" --cookies www.bilibili.com_cookies.txt`
     (Chinese source → this zh subtitle is the deliverable; no translation needed. Optionally clean it too.)
   - **YouTube English**: original zh exists → use it; original en exists → use it; **no original en → use auto `en`, clean, then translate to zh**:
     `<VPY> scripts/clean_auto_srt.py raw.en.srt clean.en.srt --txt transcript.en.txt`
     - **Punctuation-free auto-caption tracks**: some tracks strip ALL punctuation (and put a blank line between the timestamp and the text, plus 10ms "gap" cues). Symptom: `clean_auto_srt.py` prints something absurd like `cues=4136 -> segments=2` (its sentence splitter `(?<=[.!?])` never fires, so the whole talk collapses into 1-2 segments). Fallback: rerun with the dedicated cleaner `<VPY> scripts/clean_auto_srt_nopunct.py raw.en.srt clean.en.srt --txt transcript.en.txt` (skips <0.5s cues, takes each rolling cue's last line, dedups, segments by word budget / time gap; `--min-words/--gap-sec/--min-dur` tunable). Output format is identical, so `build_subs.py export` works unchanged.
   - **Captions PO-token-blocked (common on modern YouTube) → local ASR** with the reusable script (replaces the old hand-written `_asr.py`):
     `<VPY> scripts/asr_transcribe.py "<video.mp4>" _subtmp` → writes `_subtmp/asr.en.srt` + `_subtmp/asr.en.txt`. Then feed `asr.en.srt` into `clean_auto_srt.py` → translate → `build_subs.py`, same as an auto-caption track. Fix ASR proper-noun mishears using the slides/title.
5. **Translate** (only when source is non-Chinese and zh is wanted): `scripts/build_subs.py export <clean_en.srt> <OUTDIR> <BASE>`
   → `BASE.en.srt` + `BASE.segments.json`. Translate segment texts to zh (domain-accurate), save aligned
   `BASE.segments.zh.json` (**exactly same length**), then `scripts/build_subs.py build <OUTDIR> <BASE>`
   → `BASE.zh-CN.srt` + bilingual `BASE.zh-en.srt`.
6. **Plan & capture screenshots** (1920x1080, prefer slides):
   - Read the full transcript, plan ~15-25 key content moments as JSON `[{"file":"img_01_x.png","t":"MM:SS","desc":"..."}, ...]`. **Adjacent `t` values must be >10s apart** (smart_slide_capture scores a t-4s..t+6s window per shot; closer shots can pick near-identical frames). Assert the gap when building plan.json. When the user wants maximum coverage, ~1 shot per 40-60s of video is a good density.
   - **CRITICAL — derive timestamps from the actual video duration, NOT from your mental pacing.** Do NOT eyeball `MM:SS` from how "far into a ~1h talk" a topic feels; a dense talk compresses everything. Any `t` beyond the real duration → smart_slide_capture prints `FALLBACK img_xx @ MM:SS` and writes NOTHING. Instead, grep the `.en.srt` you already built for distinctive phrases of each planned shot and read their real start times, e.g. find the seconds where "Chaos Visual Debugger" / "translucency pass" / "world tick time" first appear, then use those. This guarantees every shot lands on the right content and nothing falls off the end.
   - `<VPY> scripts/smart_slide_capture.py "<video.mp4>" "<OUTDIR>/Img" plan.json`
   - Scores frames: edges + text lines + bright/uniform bg, minus skin ratio and purple-stage-curtain ratio (rejects speaker shots).
   - **Slide too small in the frame (wide auditorium shots)**: many talks are filmed wide, so the projected slide is only a small bright rectangle surrounded by black stage — the real PPT content occupies a small pixel share. `smart_slide_capture.py` now **auto-crops to the slide by default**: it detects the largest bright/edge-rich rectangle and, if it fills `< --min-frac` (default 0.55) of the frame, crops to it (16:9 + small margin) and rescales to 1920×1080 so the PPT fills the picture. Disable with `--no-crop`; tune with `--min-frac 0.5`. To fix **already-captured** images, run `<VPY> scripts/crop_to_slide.py "<OUTDIR>/Img" [--min-frac 0.55] [--dry-run] [--files img_01.png ...]` (uses `imdecode/imencode`, so CJK paths are fine). Always eyeball a few afterward — a full-screen slide capture (camera zoomed on the slide) is ideal and needs no crop.
   - **CJK / non-ASCII title folders**: OpenCV `cv2.imread/imwrite` (and thus this script's Img output) SILENTLY FAIL to write into a folder whose path has full-width brackets `【】` or other non-ASCII chars — the run "succeeds" but `Img/` ends up empty. WORKAROUND: capture into an **ASCII temp dir** (e.g. `_subtmp/cap`), then `shutil.copy` the PNGs into the real `Img/` via Python (Python file I/O handles CJK fine). Same for verifying dims: use `cv2.imdecode(np.fromfile(path))` not `cv2.imread`.
7. **Refine sparse slides (IMPORTANT)** — talks reveal bullets progressively; a captured frame may be half-empty.
   - Coverage = fraction of 32x32 blocks with any Canny edge. Flag images with coverage < ~0.13.
   - Refine plan `[{"file":"img_xx.png","t0":"MM:SS","t1":"MM:SS","ref":"img_xx.png","min_sim":0.5}]`, then:
     `<VPY> scripts/refine_fuller_frame.py "<video.mp4>" "<OUTDIR>/Img" refine_plan.json`
   - Keeps only same-slide frames (title-band match) and picks the highest content coverage. Manually override for divider/QR/richer-sibling slides.
8. **Write the note** `BASE.md` (Chinese): title/source block, 目录, sectioned content with `![](Img/img_xx.png)` at the right spots, tables, and a console-variable/quick-reference table at the end.
9. **Verify & clean**: all imgs 1920x1080; every `Img/xxx.png` referenced in the md exists; then remove **temp files only**. What to delete (none are deliverables): the whole `_subtmp/` (ASR `audio.wav` ~100MB, `asr.*.srt/.txt`, `clean.en.srt`, `transcript.en.txt`, `en_numbered.txt`, the `zh_p*.json` translation batches, any capture temp dirs), plus `_probe.json/_probe.err`. If you still hand-write per-run driver scripts (`_dl.py`/`_asr.py`), delete those too — but prefer NOT creating them: `yt_download.py --hls --no-subs` and `asr_transcribe.py` cover both, so nothing throwaway is needed. The **reusable** logic already lives permanently in `scripts/` (and mirrored in the workspace `HelperScripts/`); only the per-run intermediates are deleted. Keep the final folder to exactly: `BASE.mp4`, `BASE.en.srt` (+`.zh-CN.srt`/`.zh-en.srt` for translated talks), `BASE.md`, `Img/`.

## Pitfalls
- **CRITICAL path bug**: yt-dlp is a Windows process. A Git-Bash path `/d/foo` makes files land in `D:\d\foo`. Always pass NATIVE `D:\foo`. `yt_download.py` normalizes `/x/`→`X:\`, but drive it via a Python `subprocess.run([...])` with raw strings, and when calling the venv python from bash use ALL-forward-slash paths (mixing `\` and `/` corrupts the exe path).
- **CJK / non-ASCII folder names (e.g. B站 titles with `【】`)**: `cv2.imread`/`cv2.imwrite` can't open such paths and fail SILENTLY → screenshots don't land in `Img/`. Capture to an ASCII temp dir, then copy into `Img/` via Python `shutil`. Read images back with `cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)`. (ffmpeg itself handles CJK input paths fine; only the OpenCV read/write is the problem.) A PDF of the talk's slides, if provided, is the most reliable source of English section titles/terminology — prefer it over machine-translated AI subtitles for the note structure.
- **YouTube "Sign in to confirm you're not a bot"**: the cookie export is incomplete/stale. A valid logged-in export has `__Secure-1PSID`, `__Secure-3PSID`, `SAPISID`, `__Secure-1PAPISID`, `LOGIN_INFO` (20+ lines). Export cookies with the YouTube tab CLOSED / from a fresh logged-in session, then retry. Updating yt-dlp to the latest `--pre` nightly also helps.
- **YouTube "tv downgraded player" → only 360p (format 18) + "has no automatic captions"**: the default probe got a downgraded player. Add `--extractor-args "youtube:player_client=web_safari,web"` to expose 720p/1080p (formats 300/301; en-US original = `301-14`). Those are often **HLS m3u8 only** (DASH is PO-token-gated).
- **HLS download trips the sandbox bulk-delete guard** (`SAFE_DELETE_BULK_CONFIRM_REQUIRED`): native HLS writes 300+ `.part-FragN` files and deletes each after merge, killing the run. Fix: `--downloader ffmpeg --hls-prefer-ffmpeg` so ffmpeg streams the m3u8 into one mp4 (no per-fragment temp files). Custom `-f "301/301-14/300/best[height<=1080]"`.
- **No downloadable subtitles at all (PO token wall on captions)** → **local ASR fallback**: `pip install faster-whisper`; `ffmpeg -i v.mp4 -ac 1 -ar 16000 audio.wav`; `WhisperModel("small.en", device="cpu", compute_type="int8")` + `vad_filter=True`, write SRT from segments (~7 min for a 37-min talk on CPU, incl. one-time model download). Then treat it as the raw en SRT → clean_auto_srt → translate → build_subs, same as auto-captions. Fix obvious ASR mishears from the slides (e.g. "Urban solver"→"RBAN solver").
- **Hand-written zh JSON breaks on inner ASCII quotes**: a translated line containing `"` (as CJK emphasis) invalidates the JSON array. Use CJK quotes `“ ”`, or run a repair pass converting inner straight quotes to paired `“ ”` before `json.load`. Keep zh length == en segment count. **Generate batch files with a Python `_rebuild_pXX.py` script** (entries list + `json.dumps(ensure_ascii=False)`) instead of heredocs — bash heredocs with embedded Python + CJK mis-parse quotes. Write the output as a path **relative to the script's CWD** (`zh_pXX.json`), NOT `_subtmp/zh_pXX.json`, when the script itself lives/runs inside `_subtmp/` (double nesting → FileNotFoundError).
- **Auto-caption track with NO punctuation** (`clean_auto_srt.py` → `segments=2`): the sentence splitter never fires. Also common in such tracks: blank line between timestamp and text (standard block parser loses that text), 10ms gap cues, and each line repeated ~3 cues. Use `clean_auto_srt_nopunct.py` (see Step 4). Real case: "New Features of Insights" (af_M38Z325I), 4136 cues → 838 clean segments.
- **Bilibili AI subtitles come back empty**: (1) MUST send `Referer: https://search.bilibili.com/` (the `www.bilibili.com` referer returns an empty list); (2) do NOT reuse one httpx.Client across the `view` + `player/v2` calls — response Set-Cookie clobbers SESSDATA; send the Cookie header per request (bili_subs.py does this); (3) the player/v2 subtitle list is flaky under rapid access — retry a few times (bili_subs.py retries 5x). Verify login with `x/web-interface/nav` (`isLogin=True`).
- **Subtitle 1:1 alignment** (translation): zh array length MUST equal en segment count. Spot-check anchors; on drift, binary-search the first mismatch (merged/skipped segment) and splice.
- **Speaker vs slide / half-empty slides**: always run Step 7. The fullest version of a slide is usually a few seconds LATER than first mention. The very first title slide is usually within the first ~5s.

## Verification
- `ffmpeg -i video.mp4` shows `1920x1080` (or higher) and expected duration.
- Subtitles present (zh-CN always; +en/zh-en for translated English talks); if translated, zh-CN line count == en segment count.
- All `Img/*.png` are 1920x1080; every image referenced in the md resolves.
- Folder == video title; `video.mp4` and `note.md` share the exact base name.

## Scripts
- `@scripts/setup_env.py`         — create isolated venv + install yt-dlp[default]/ffmpeg/opencv/numpy/httpx (+faster-whisper for ASR).
- `@scripts/yt_download.py`       — platform-aware download (>=1080p mp4 + subs); auto cookie + Node(YT only). `--hls`=web_safari+ffmpeg HLS for modern-YouTube 1080p; `--no-subs`=skip PO-token-blocked captions.
- `@scripts/asr_transcribe.py`    — local ASR fallback (ffmpeg 16k mono → faster-whisper) → `asr.<lang>.srt`+`.txt`, for PO-token-blocked / caption-less videos.
- `@scripts/bili_subs.py`         — fetch Bilibili AI/uploaded subtitle (ai-zh) as SRT via player/v2 API (fallback for yt-dlp).
- `@scripts/clean_auto_srt.py`    — dedupe rolling auto-captions / ASR into clean sentence segments.
- `@scripts/clean_auto_srt_nopunct.py` — cleaner for punctuation-free auto-caption tracks (blank-line cues, 10ms gap cues, rolling repeats); segments by word budget / time gap. Drop-in replacement when clean_auto_srt collapses the talk into 1-2 segments.
- `@scripts/build_subs.py`        — export segments for translation, then build zh-CN + bilingual SRTs.
- `@scripts/smart_slide_capture.py` — pick the most slide-like frame near each timestamp, save 1920x1080; **auto-crops to the slide** when it's a small rectangle in a wide shot (`--no-crop`/`--min-frac`).
- `@scripts/refine_fuller_frame.py` — replace a half-empty slide with a fuller frame of the same slide.
- `@scripts/crop_to_slide.py`     — post-process: crop already-captured images to the slide bbox + rescale to 1920x1080 when the PPT occupies too little of the frame.
