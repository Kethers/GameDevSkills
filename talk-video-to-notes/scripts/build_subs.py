"""
Build final subtitle files for a downloaded talk from a cleaned English SRT.

Steps:
  1. Read cleaned English SRT (from clean_auto_srt.py).
  2. Write <base>.en.srt into target folder (copy, renumbered).
  3. Export segments to <base>.segments.json for translation.
  4. (After translation JSON is filled) merge Chinese back to produce
     <base>.zh-CN.srt and bilingual <base>.zh-en.srt.

Usage:
  # phase 1: export
  python build_subs.py export <clean_en.srt> <target_dir> <base>
  # phase 2: after writing zh into <base>.segments.zh.json, build zh + bilingual
  python build_subs.py build <target_dir> <base>
"""
import sys, os, re, json

def parse_srt(path):
    with open(path, encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'\n\s*\n', content.strip())
    out = []
    for b in blocks:
        lines = [l for l in b.splitlines() if l.strip()]
        if len(lines) < 2: continue
        ti = next((i for i,l in enumerate(lines) if '-->' in l), None)
        if ti is None: continue
        m = re.search(r'([\d:,\.]+)\s*-->\s*([\d:,\.]+)', lines[ti])
        if not m: continue
        text = ' '.join(lines[ti+1:]).strip()
        out.append({'start': m.group(1), 'end': m.group(2), 'text': text})
    return out

def write_srt(segs, path, key='text'):
    with open(path, 'w', encoding='utf-8') as f:
        for i,s in enumerate(segs, 1):
            f.write(f"{i}\n{s['start']} --> {s['end']}\n{s[key]}\n\n")

def write_bilingual(segs, path):
    with open(path, 'w', encoding='utf-8') as f:
        for i,s in enumerate(segs, 1):
            f.write(f"{i}\n{s['start']} --> {s['end']}\n{s['zh']}\n{s['text']}\n\n")

def main():
    mode = sys.argv[1]
    if mode == 'export':
        clean, tdir, base = sys.argv[2], sys.argv[3], sys.argv[4]
        segs = parse_srt(clean)
        os.makedirs(tdir, exist_ok=True)
        write_srt(segs, os.path.join(tdir, base + '.en.srt'))
        with open(os.path.join(tdir, base + '.segments.json'), 'w', encoding='utf-8') as f:
            json.dump(segs, f, ensure_ascii=False, indent=1)
        print(f"exported {len(segs)} segments; wrote {base}.en.srt and {base}.segments.json")
    elif mode == 'build':
        tdir, base = sys.argv[2], sys.argv[3]
        segs = json.load(open(os.path.join(tdir, base + '.segments.json'), encoding='utf-8'))
        zh = json.load(open(os.path.join(tdir, base + '.segments.zh.json'), encoding='utf-8'))
        assert len(zh) == len(segs), f"zh count {len(zh)} != en count {len(segs)}"
        for s, z in zip(segs, zh):
            s['zh'] = z if isinstance(z, str) else z.get('zh', '')
        write_srt(segs, os.path.join(tdir, base + '.zh-CN.srt'), key='zh')
        write_bilingual(segs, os.path.join(tdir, base + '.zh-en.srt'))
        print(f"built {base}.zh-CN.srt and {base}.zh-en.srt ({len(segs)} segments)")

if __name__ == '__main__':
    main()
