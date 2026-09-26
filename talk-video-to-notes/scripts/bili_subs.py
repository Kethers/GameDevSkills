"""
Fetch Bilibili subtitles (AI 字幕 / uploaded 字幕) as SRT.

Bilibili's AI subtitles are exposed via the player/v2 API and require a logged-in
cookie AND a Referer of https://search.bilibili.com/ (an empirically important quirk —
with Referer https://www.bilibili.com/ the subtitle list often comes back empty).

yt-dlp can download the video/danmaku for bilibili, but frequently misses the AI
subtitle track; this script is the reliable fallback for the subtitle itself.

Usage:
  python bili_subs.py <bvid_or_url> <out_srt_path> [--cookies www.bilibili.com_cookies.txt] [--page 1]

Requires: httpx  (pip install httpx into the venv)
"""
import sys, os, re, json, argparse

def parse_netscape_cookies(path):
    c = {}
    if not path or not os.path.exists(path):
        return c
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        p = line.split('\t')
        if len(p) >= 7:
            c[p[5]] = p[6]
    return c

def bvid_from(url):
    m = re.search(r'(BV[0-9A-Za-z]+)', url)
    if m:
        return m.group(1)
    return url  # assume already a bvid

def fmt(t):
    t = float(t); h = int(t//3600); m = int((t % 3600)//60); s = int(t % 60); ms = int((t % 1)*1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'

def main():
    import httpx
    ap = argparse.ArgumentParser()
    ap.add_argument('url'); ap.add_argument('out')
    ap.add_argument('--cookies', default=os.environ.get('BILI_COOKIES', ''))
    ap.add_argument('--page', type=int, default=1)
    a = ap.parse_args()

    bvid = bvid_from(a.url)
    cookies = parse_netscape_cookies(a.cookies)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Referer': 'https://search.bilibili.com/',  # IMPORTANT: gates the subtitle list
        'Cookie': '; '.join(f'{k}={v}' for k, v in cookies.items()),
    }
    # NOTE: use a fresh client per request and re-send the Cookie header every time.
    # A persistent httpx.Client merges Set-Cookie from the `view` response into its jar,
    # which can clobber SESSDATA and make the subsequent player/v2 return an empty
    # subtitle list. Sending the header explicitly each call avoids that.
    def get_json(url):
        with httpx.Client(follow_redirects=True) as cli:
            return cli.get(url, headers=headers, timeout=20).json()
    def get_raw(url):
        with httpx.Client(follow_redirects=True) as cli:
            return cli.get(url, headers=headers, timeout=20)

    if True:
        v = get_json(f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}')
        if v.get('code') != 0:
            print('view API error:', v.get('message')); sys.exit(2)
        data = v['data']
        aid = data['aid']
        pages = data.get('pages', [])
        cid = data['cid'] if a.page == 1 else pages[a.page-1]['cid']
        title = data['title']
        print(f'Title: {title}\naid={aid} cid={cid} duration={data.get("duration")}s')

        # player/v2 subtitle list is flaky under rapid access — retry a few times.
        import time as _t
        subs = []
        for attempt in range(5):
            p = get_json(f'https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}')
            subs = (((p.get('data') or {}).get('subtitle') or {}).get('subtitles')) or []
            if subs:
                break
            _t.sleep(2.0)
        print(f'subtitle tracks: {[(s.get("lan"), s.get("lan_doc")) for s in subs]}')

        if not subs:
            print('NO subtitle tracks found after retries (video may genuinely have none).')
            sys.exit(3)

        # prefer human zh > ai-zh > first
        def rank(s):
            lan = s.get('lan', '')
            if lan in ('zh-CN', 'zh-Hans'): return 0
            if lan.startswith('zh'): return 1
            if lan == 'ai-zh': return 2
            if lan.startswith('ai-zh'): return 3
            return 9
        subs.sort(key=rank)
        chosen = subs[0]
        url = chosen.get('subtitle_url', '')
        if url.startswith('//'):
            url = 'https:' + url
        body = []
        for attempt in range(4):
            try:
                body = get_raw(url).json().get('body', [])
                break
            except Exception as e:
                if attempt == 3:
                    print('subtitle download failed:', e); sys.exit(4)
                import time as _t; _t.sleep(1.5)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as f:
            for i, line in enumerate(body, 1):
                f.write(f"{i}\n{fmt(line.get('from',0))} --> {fmt(line.get('to',0))}\n{line.get('content','')}\n\n")
        print(f'saved {len(body)} lines ({chosen.get("lan")}) -> {a.out}')

if __name__ == '__main__':
    main()
