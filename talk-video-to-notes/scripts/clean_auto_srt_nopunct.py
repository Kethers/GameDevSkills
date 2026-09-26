"""
Clean YouTube auto-generated SRT tracks that LACK PUNCTUATION (and often have
blank lines between the timestamp and the text, plus 10ms "gap" cues).

Why this exists: clean_auto_srt.py splits the reconstructed transcript into
sentence-ish segments with `re.split(r'(?<=[.!?])\\s+')`. If the auto-caption
track has no punctuation at all, the WHOLE transcript collapses into 1-2
segments (symptom: `cues=4136 -> segments=2`). Such tracks also commonly:
  - repeat each rolling line across ~3 consecutive cues,
  - insert a blank line between the timestamp line and the text,
  - contain spurious cues whose duration is ~10ms.

Strategy per cue: skip cues shorter than --min-dur (default 0.5s); take the
LAST non-empty text line (that is the new line of a rolling two-line cue);
skip bracketed noise ([Music], [Applause], ...). Then drop consecutive
duplicate lines, and segment the stream by word budget (>= --min-words,
default 14) or by a time gap between lines (> --gap-sec, default 3.5s).

Usage (drop-in replacement for clean_auto_srt.py):
  python clean_auto_srt_nopunct.py <input.srt> <output_clean.srt> [--txt output.txt]
      [--min-words 14] [--gap-sec 3.5] [--min-dur 0.5]

Output SRT/txt formats are identical to clean_auto_srt.py (txt line = `[HH:MM:SS] text`,
line number == segment idx), so build_subs.py export works unchanged downstream.
"""
import sys, re, argparse

CUE_RE = re.compile(
    r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)',
    re.S,
)
NOISE_RE = re.compile(r'^\[.*\]$|^foreign$|^music$|^applause$|^laughter$', re.I)


def to_sec(ts):
    ts = ts.replace(',', '.')
    h, m, s = ts.split(':')
    return int(h)*3600 + int(m)*60 + float(s)


def to_ts(sec):
    h = int(sec//3600); m = int((sec%3600)//60); s = int(sec%60); ms = int(round((sec-int(sec))*1000))
    if ms == 1000:
        s += 1; ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_lines(path, min_dur):
    """Yield (start_sec, text) per surviving cue line."""
    content = open(path, encoding='utf-8').read()
    out = []
    for m in CUE_RE.finditer(content):
        start_s, end_s, body = m.group(1), m.group(2), m.group(3)
        st, en = to_sec(start_s), to_sec(end_s)
        if en - st < min_dur:          # 10ms gap cues and other spurious blips
            continue
        lines = [l.strip() for l in body.splitlines() if l.strip()]
        if not lines:
            continue
        text = lines[-1]               # last non-empty line = new line of rolling cue
        if NOISE_RE.match(text):
            continue
        out.append((st, text))
    # drop consecutive duplicates (rolling repeats)
    dedup = []
    for st, text in out:
        if dedup and dedup[-1][1] == text:
            continue
        dedup.append((st, text))
    return dedup


def segment(lines, min_words, gap_sec):
    """Merge (start, text) lines into segments by word budget / time gap."""
    segs = []
    buf, buf_start, wc, prev_st = [], None, 0, None
    for st, text in lines:
        if prev_st is not None and (st - prev_st) > gap_sec and buf:
            segs.append((buf_start, prev_st, ' '.join(buf)))
            buf, buf_start, wc = [], None, 0
        if not buf:
            buf_start = st
        buf.append(text)
        wc += len(text.split())
        prev_st = st
        if wc >= min_words:
            segs.append((buf_start, st, ' '.join(buf)))
            buf, buf_start, wc, prev_st = [], None, 0, None
    if buf:
        segs.append((buf_start, prev_st, ' '.join(buf)))
    # sanitize durations
    fixed = []
    for s, e, t in segs:
        if e is None or e <= s:
            e = s + 2
        fixed.append((s, e, t))
    return fixed


def write_srt(segs, path):
    with open(path, 'w', encoding='utf-8') as f:
        for i, (s, e, t) in enumerate(segs, 1):
            f.write(f"{i}\n{to_ts(s)} --> {to_ts(e)}\n{t}\n\n")


def write_txt(segs, path):
    with open(path, 'w', encoding='utf-8') as f:
        for s, e, t in segs:
            f.write(f"[{to_ts(s)[:8]}] {t}\n")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('inp'); ap.add_argument('out'); ap.add_argument('--txt')
    ap.add_argument('--min-words', type=int, default=14)
    ap.add_argument('--gap-sec', type=float, default=3.5)
    ap.add_argument('--min-dur', type=float, default=0.5)
    a = ap.parse_args()
    lines = parse_lines(a.inp, a.min_dur)
    segs = segment(lines, a.min_words, a.gap_sec)
    write_srt(segs, a.out)
    if a.txt:
        write_txt(segs, a.txt)
    print(f"lines={len(lines)} -> segments={len(segs)}; wrote {a.out}")
