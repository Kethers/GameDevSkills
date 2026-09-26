"""
Refine slide screenshots: for a slide that was captured while only partially
revealed (lots of blank space), search a time window for a frame showing the
SAME slide but with MORE content (later builds add bullets/images), and save it.

Strategy per target:
  - Sample frames across [t_start, t_end] every `step` seconds.
  - Keep only "slide-like" frames (low purple-stage ratio, low skin) so we don't
    jump to a speaker cutaway or a different slide.
  - Among those, pick the frame with the HIGHEST content coverage (32x32 edge blocks).
  - Optionally require the top region (title band) to stay similar to the original
    so we keep the same slide, not the next one.

Usage:
  python refine_fuller_frame.py <video> <img_dir> <plan_json>
plan_json: [{"file":"img_06_x.png","t0":"05:50","t1":"06:20","ref":"img_06_x.png"}, ...]
  t0..t1 = search window (mm:ss or hh:mm:ss); ref = existing image to compare title band.
"""
import sys, os, json, subprocess, tempfile
import numpy as np, cv2

def _find_ffmpeg():
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

FFMPEG=_find_ffmpeg()

def ts(s):
    p=[float(x) for x in s.split(':')]
    if len(p)==3:return p[0]*3600+p[1]*60+p[2]
    if len(p)==2:return p[0]*60+p[1]
    return p[0]

def grab(video,sec,out):
    cmd=[FFMPEG,'-hide_banner','-loglevel','error','-ss',f'{sec:.3f}','-i',video,
         '-frames:v','1','-q:v','2','-vf','scale=1920:1080','-y',out]
    return subprocess.run(cmd,capture_output=True).returncode==0 and os.path.exists(out)

def coverage(img):
    g=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY);e=cv2.Canny(g,80,180)
    h,w=e.shape;bs=32;cov=0;tot=0
    for y in range(0,h,bs):
        for x in range(0,w,bs):
            tot+=1
            if e[y:y+bs,x:x+bs].sum()>0:cov+=1
    return cov/tot

def stage_ratio(img):
    hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV);h,s,v=hsv[:,:,0],hsv[:,:,1],hsv[:,:,2]
    return float(((h>=120)&(h<=170)&(s>60)&(v>30)).mean())

def skin_ratio(img):
    y=cv2.cvtColor(img,cv2.COLOR_BGR2YCrCb);cr=y[:,:,1];cb=y[:,:,2]
    return float(((cr>135)&(cr<180)&(cb>85)&(cb<135)).mean())

def title_band(img):
    # top 22% grayscale, downscaled — used to check same-slide continuity
    g=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    band=g[0:int(g.shape[0]*0.22),:]
    return cv2.resize(band,(160,24)).astype(np.float32)

def band_sim(a,b):
    a=(a-a.mean());b=(b-b.mean())
    d=np.sqrt((a*a).sum())*np.sqrt((b*b).sum())
    if d==0:return 0.0
    return float((a*b).sum()/d)

def main():
    video,img_dir,plan=sys.argv[1],sys.argv[2],sys.argv[3]
    items=json.load(open(plan,encoding='utf-8'))
    with tempfile.TemporaryDirectory() as tmp:
        for it in items:
            t0,t1=ts(it['t0']),ts(it['t1'])
            step=it.get('step',1.0)
            ref_path=os.path.join(img_dir,it.get('ref',it['file']))
            ref_band=title_band(cv2.imread(ref_path)) if os.path.exists(ref_path) else None
            need_same=it.get('same_slide',True)
            best=None
            s=t0
            while s<=t1:
                p=os.path.join(tmp,f"{it['file']}_{int(s*1000)}.png")
                if grab(video,s,p):
                    im=cv2.imread(p)
                    if im is not None:
                        st=stage_ratio(im);sk=skin_ratio(im)
                        if st<0.15 and sk<0.05:
                            cov=coverage(im)
                            sim=band_sim(ref_band,title_band(im)) if ref_band is not None else 1.0
                            ok=(sim>=it.get('min_sim',0.5)) if need_same else True
                            if ok and (best is None or cov>best[0]):
                                best=(cov,s,p,sim,st,sk)
                s+=step
            out=os.path.join(img_dir,it['file'])
            if best is None:
                print(f"SKIP {it['file']} (no better slide frame found)")
                continue
            cov,s,p,sim,st,sk=best
            cv2.imwrite(out,cv2.imread(p))
            print(f"OK {it['file']} -> t={s:.1f}s coverage={cov:.3f} sim={sim:.2f} stage={st:.3f} skin={sk:.3f}")
    print("done")

if __name__=='__main__':
    main()
