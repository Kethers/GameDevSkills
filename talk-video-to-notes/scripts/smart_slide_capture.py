"""
Smart slide-frame capture for talk/presentation videos.

For each requested timestamp, sample several candidate frames in a +/- window,
score each for "slide-likeness", and save the best one at 1920x1080 into an Img folder.

Slide vs. speaker heuristic (higher score = more slide-like):
  + high edge density outside center (text/diagrams fill the frame)
  + large near-uniform bright regions (slide background)
  + presence of strong horizontal/vertical structure (text lines, UI)
  - large skin-tone area (speaker face/hands, camera shot of person)
  - very dark, low-texture photographic frames (stage/speaker close-up)

Usage:
  python smart_slide_capture.py <video> <img_dir> <plan_json>
plan_json: [{"file":"img_01_intro.png","t":"00:00:05","desc":"..."}, ...]
For each item, searches t-4s .. t+6s.

Requires: opencv-python-headless, numpy, ffmpeg (path below).
"""
import sys, os, json, subprocess, tempfile
import numpy as np
import cv2

def _find_ffmpeg():
    # env override
    env = os.environ.get("YT_FFMPEG")
    if env and os.path.exists(env):
        return env
    home = os.path.expanduser("~")
    for c in (os.path.join(home, ".workbuddy", "binaries", "ffmpeg", "bin", "ffmpeg.exe"),
              os.path.join(home, ".workbuddy", "binaries", "ffmpeg", "bin", "ffmpeg")):
        if os.path.exists(c):
            return c
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        from shutil import which
        return which("ffmpeg") or "ffmpeg"

FFMPEG = _find_ffmpeg()

def ts_to_sec(ts):
    p = ts.split(':')
    p = [float(x) for x in p]
    if len(p) == 3: return p[0]*3600+p[1]*60+p[2]
    if len(p) == 2: return p[0]*60+p[1]
    return p[0]

def sec_to_ts(s):
    h=int(s//3600); m=int((s%3600)//60); sec=s-h*3600-m*60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"

def grab(video, sec, out_png):
    cmd=[FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{sec:.3f}','-i',video,
         '-frames:v','1','-q:v','2','-vf','scale=1920:1080','-y',out_png]
    r=subprocess.run(cmd,capture_output=True)
    return r.returncode==0 and os.path.exists(out_png)

def skin_ratio(img):
    ycrcb=cv2.cvtColor(img,cv2.COLOR_BGR2YCrCb)
    cr=ycrcb[:,:,1]; cb=ycrcb[:,:,2]
    mask=(cr>135)&(cr<180)&(cb>85)&(cb<135)
    return float(mask.mean())

def bright_uniform_ratio(gray):
    # fraction of pixels that are bright and locally flat (typical slide bg)
    bright=gray>170
    blur=cv2.blur(gray,(9,9)).astype(np.int16)
    flat=np.abs(gray.astype(np.int16)-blur)<8
    return float((bright&flat).mean())

def edge_density(gray):
    e=cv2.Canny(gray,80,180)
    return float((e>0).mean())

def text_structure(gray):
    # count strong horizontal runs (text lines) via row-wise edge sums
    e=cv2.Canny(gray,80,180)
    row=e.sum(axis=1)
    thr=row.mean()+row.std()
    lines=int((row>thr).sum())
    return lines/gray.shape[0]

def stage_ratio(img):
    # Detect purple/magenta stage-curtain pixels typical of the speaker shots.
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
    h=hsv[:,:,0]; s=hsv[:,:,1]; v=hsv[:,:,2]
    # OpenCV hue 0-179; purple/magenta ~ 125-165, moderate+ saturation
    purple=((h>=120)&(h<=170)&(s>60)&(v>30))
    return float(purple.mean())

def slide_score(img):
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    ed=edge_density(gray)
    bu=bright_uniform_ratio(gray)
    ts=text_structure(gray)
    sk=skin_ratio(img)
    st=stage_ratio(img)
    # Slides: many crisp edges + text lines + (bright OR pure-black bg, low saturation).
    # Speaker shots: purple curtain (high stage), some skin, few text lines.
    score = ed*2.0 + bu*1.5 + ts*1.5 - sk*4.0 - st*3.0
    return score, dict(edge=round(ed,3),bright=round(bu,3),text=round(ts,3),skin=round(sk,3),stage=round(st,3))

def detect_slide_bbox(img):
    """Find the bounding box of the projected slide inside a wide auditorium frame.

    In many talk recordings the actual slide is a bright, high-edge rectangle
    surrounded by dark stage. We threshold "content" (bright OR edge-rich) pixels,
    take the largest connected region, and return its bbox + the fraction of the
    frame it occupies. Returns (x,y,w,h,frac) or None.
    """
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    H,W=gray.shape
    edges=cv2.Canny(gray,60,160)
    edges=cv2.dilate(edges,np.ones((15,15),np.uint8),iterations=1)
    bright=(gray>60).astype(np.uint8)*255   # anything not near-black stage
    content=cv2.bitwise_or(edges,bright)
    content=cv2.morphologyEx(content,cv2.MORPH_CLOSE,np.ones((25,25),np.uint8))
    cnts,_=cv2.findContours(content,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    best=max(cnts,key=cv2.contourArea)
    x,y,w,h=cv2.boundingRect(best)
    frac=(w*h)/float(W*H)
    return (x,y,w,h,frac)

def crop_to_slide(img, min_frac=0.55, margin=0.02):
    """If the slide occupies < min_frac of the frame, crop to the slide bbox
    (with a small margin), preserving 16:9, and rescale to 1920x1080 so the PPT
    content fills the picture. Returns a 1920x1080 image (cropped or original)."""
    H,W=img.shape[:2]
    bb=detect_slide_bbox(img)
    if bb is None:
        return img, 1.0
    x,y,w,h,frac=bb
    if frac>=min_frac or w<W*0.25 or h<H*0.25:
        return img, frac  # already fills enough, or bbox implausibly small -> leave as-is
    # expand by margin, clamp
    mx=int(W*margin); my=int(H*margin)
    x0=max(0,x-mx); y0=max(0,y-my); x1=min(W,x+w+mx); y1=min(H,y+h+my)
    # force 16:9 around the bbox center
    cw=x1-x0; ch=y1-y0
    target=16/9
    if cw/ch>target:      # too wide -> grow height
        nh=int(cw/target); cy=(y0+y1)//2
        y0=max(0,cy-nh//2); y1=min(H,y0+nh); y0=max(0,y1-nh)
    else:                 # too tall -> grow width
        nw=int(ch*target); cx=(x0+x1)//2
        x0=max(0,cx-nw//2); x1=min(W,x0+nw); x0=max(0,x1-nw)
    crop=img[y0:y1, x0:x1]
    if crop.size==0:
        return img, frac
    crop=cv2.resize(crop,(1920,1080),interpolation=cv2.INTER_CUBIC)
    return crop, frac

def pick_best(video, center_sec, img_dir, tmp):
    # sample a wide window around the center to find a slide even if the exact
    # timestamp is a speaker cutaway.
    cands=[]
    for off in [ -8,-6,-4,-3,-2,-1,0,1,2,3,4,6,8,10,12 ]:
        s=max(0.5, center_sec+off)
        p=os.path.join(tmp, f'c_{int(s*1000)}.png')
        if grab(video, s, p):
            img=cv2.imread(p)
            if img is None: continue
            sc,det=slide_score(img)
            cands.append((sc,s,p,det))
    if not cands:
        return None
    cands.sort(key=lambda x:x[0], reverse=True)
    return cands[0]

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("video"); ap.add_argument("img_dir"); ap.add_argument("plan_json")
    ap.add_argument("--no-crop", action="store_true",
                    help="Disable auto-crop-to-slide (by default, if the projected slide fills "
                         "< --min-frac of a wide auditorium frame, crop to it and rescale to 1920x1080).")
    ap.add_argument("--min-frac", type=float, default=0.55,
                    help="If the detected slide occupies less than this fraction of the frame, crop to it.")
    a=ap.parse_args()
    video, img_dir, plan_json = a.video, a.img_dir, a.plan_json
    os.makedirs(img_dir, exist_ok=True)
    plan=json.load(open(plan_json,encoding='utf-8'))
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        for item in plan:
            center=ts_to_sec(item['t'])
            best=pick_best(video, center, img_dir, tmp)
            outp=os.path.join(img_dir, item['file'])
            if best is None:
                grab(video, center, outp)
                results.append((item['file'], item['t'], 'fallback', {}))
                print(f"FALLBACK {item['file']} @ {item['t']}")
                continue
            sc,s,p,det=best
            img=cv2.imread(p)
            note=""
            if not a.no_crop:
                cropped,frac=crop_to_slide(img, min_frac=a.min_frac)
                if cropped is not img:
                    note=f" [cropped: slide was {frac:.0%} of frame]"
                    img=cropped
            cv2.imwrite(outp,img)
            results.append((item['file'], sec_to_ts(s), round(sc,2), det))
            print(f"OK {item['file']} chosen@{s:.1f}s score={sc:.2f} {det}{note} ({item['desc']})")
    print(f"\nDone. {len(results)} images -> {img_dir}")

if __name__=='__main__':
    main()
