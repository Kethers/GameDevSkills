"""
Clean YouTube auto-generated SRT (rolling/duplicated captions) into a de-duplicated
transcript. Auto-captions repeat each phrase across 2-3 cues and split lines mid-sentence;
this reconstructs a readable transcript with a timestamp per merged segment.

Usage:
  python clean_auto_srt.py <input.srt> <output_clean.srt> [--txt output.txt]

Output SRT: merged cues (start=first appearance, end=last), one segment per ~sentence chunk.
"""
import sys, re, argparse

def parse_srt(path):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'\n\s*\n', content.strip())
    cues = []
    for b in blocks:
        lines = [l for l in b.splitlines() if l.strip() != '']
        if len(lines) < 2:
            continue
        # find timestamp line
        ts_idx = None
        for i, l in enumerate(lines):
            if '-->' in l:
                ts_idx = i; break
        if ts_idx is None:
            continue
        m = re.search(r'(\d\d:\d\d:\d\d[,\.]\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d[,\.]\d\d\d)', lines[ts_idx])
        if not m:
            continue
        start, end = m.group(1), m.group(2)
        text = ' '.join(lines[ts_idx+1:]).strip()
        if text:
            cues.append((start, end, text))
    return cues

def to_sec(ts):
    ts = ts.replace(',', '.')
    h, m, s = ts.split(':')
    return int(h)*3600 + int(m)*60 + float(s)

def to_ts(sec):
    h = int(sec//3600); m = int((sec%3600)//60); s = int(sec%60); ms = int(round((sec-int(sec))*1000))
    if ms == 1000:
        s += 1; ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def clean(cues):
    # Auto captions: each new cue often = previous tail line + new line.
    # Strategy: walk cues, keep a growing token stream but only append text not already
    # present at the tail. Reconstruct full transcript, tracking earliest time per word run.
    words = []          # list of (word, start_sec)
    for start, end, text in cues:
        toks = text.split()
        st = to_sec(start)
        # find longest suffix of existing words that matches a prefix of toks (overlap)
        # to avoid duplicating rolling text
        max_ov = 0
        maxk = min(len(toks), len(words), 40)
        for k in range(maxk, 0, -1):
            if [w for w,_ in words[-k:]] == toks[:k]:
                max_ov = k; break
        for w in toks[max_ov:]:
            words.append((w, st))
    # Rebuild sentences and assign timestamp = time of first word in the segment.
    full = ' '.join(w for w,_ in words)
    # split into sentence-ish segments
    segs = re.split(r'(?<=[.!?])\s+', full)
    # map: we need start time per segment -> find index in words
    out = []
    wi = 0
    for seg in segs:
        seg = seg.strip()
        if not seg:
            continue
        n = len(seg.split())
        if wi >= len(words):
            start_sec = words[-1][1] if words else 0
        else:
            start_sec = words[wi][1]
        wi += n
        end_sec = words[min(wi, len(words)-1)][1] if words else start_sec
        if end_sec <= start_sec:
            end_sec = start_sec + 2
        out.append((start_sec, end_sec, seg))
    return out

def write_srt(segs, path):
    with open(path, 'w', encoding='utf-8') as f:
        for i,(s,e,t) in enumerate(segs, 1):
            f.write(f"{i}\n{to_ts(s)} --> {to_ts(e)}\n{t}\n\n")

def write_txt(segs, path):
    with open(path, 'w', encoding='utf-8') as f:
        for s,e,t in segs:
            f.write(f"[{to_ts(s)[:8]}] {t}\n")

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('inp'); ap.add_argument('out'); ap.add_argument('--txt')
    a = ap.parse_args()
    cues = parse_srt(a.inp)
    segs = clean(cues)
    write_srt(segs, a.out)
    if a.txt:
        write_txt(segs, a.txt)
    print(f"cues={len(cues)} -> segments={len(segs)}; wrote {a.out}")
