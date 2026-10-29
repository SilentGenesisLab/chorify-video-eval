"""用 ffmpeg 合成参数已知的测试素材。结果按参数哈希缓存在系统临时目录，重复运行不重新编码。

所有素材都用 testsrc2（持续运动的画面）做底：纯色画面会被 freezedetect 判成冻结，
会让测试自己先出错。
"""
import hashlib
import subprocess
import tempfile
from pathlib import Path

import video_review as vr

CACHE = Path(tempfile.gettempdir()) / "vr_test_media"
H264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]


def ffmpeg(*args):
    p = subprocess.run([vr.ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
                       capture_output=True, text=True, errors="replace")
    if p.returncode:
        raise RuntimeError(f"ffmpeg 失败：{p.stderr[-500:]}")


def make(name, *args, src=None):
    """name 决定扩展名；args 为 ffmpeg 参数（输出路径自动追加）。src 为需要先生成的输入。"""
    key = hashlib.sha1(repr((name, args, vr.ffmpeg_exe())).encode()).hexdigest()[:12]
    CACHE.mkdir(exist_ok=True)
    out = CACHE / f"{key}_{name}"
    if not out.exists():
        tmp = out.with_name("tmp_" + out.name)
        ffmpeg(*[str(src) if a == "{src}" else a for a in args], tmp)
        tmp.replace(out)
    return out


def video(w=320, h=180, fps=30, dur=4, vf=None, audio=None, ext="mp4"):
    """audio：None 无音轨；数字 = 双声道 997Hz 正弦幅度；'silence' 静音。"""
    args = ["-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r={fps}:d={dur}"]
    if audio == "silence":
        args += ["-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo"]
    elif audio is not None:
        args += ["-f", "lavfi", "-i", f"aevalsrc={audio}*sin(2*PI*997*t)|{audio}*sin(2*PI*997*t):s=48000:d={dur}"]
    if vf:
        args += ["-vf", vf]
    if ext == "webm":
        args += ["-c:v", "libvpx-vp9", "-b:v", "200k"] + (["-c:a", "libopus"] if audio is not None else ["-an"])
    else:
        args += H264 + (["-c:a", "aac", "-b:a", "192k"] if audio is not None else ["-an"])
    if audio is not None:
        args += ["-shortest"]
    return make(f"v{w}x{h}_{fps}_{dur}.{ext}", *args)


def black_segment(start, end, dur=4):
    return video(dur=dur, vf=f"drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,{start},{end})'")


def freeze_at(start_frame, n_frames, dur=8, fps=30):
    return video(dur=dur, fps=fps, vf=f"loop=loop={n_frames}:size=1:start={start_frame},trim=duration={dur},setpts=N/{fps}/TB")


def rotated(deg=90):
    land = video(dur=1)
    return make(f"rot{deg}.mp4", "-display_rotation", str(deg), "-i", "{src}", "-c", "copy", src=land)


def audio_longer_than_video(vdur=2, adur=4):
    return make(f"long_audio_{vdur}_{adur}.mp4", "-f", "lavfi", "-i", f"testsrc2=s=320x180:r=30:d={vdur}",
                "-f", "lavfi", "-i", f"sine=f=997:r=48000:d={adur}", *H264, "-ac", "2", "-c:a", "aac")


def audio_only(dur=3):
    return make(f"audio_{dur}.m4a", "-f", "lavfi", "-i", f"sine=f=997:r=48000:d={dur}", "-c:a", "aac")


def frame_index_video(fps=25, dur=10):
    """每帧把自己的帧号编码进亮度：上半 = floor(N/16)*16，下半 = (N%16)*16+8。无损编码，帧号 < 256。"""
    assert fps * dur < 256
    return make(f"idx_{fps}_{dur}.mp4", "-f", "lavfi", "-i", f"nullsrc=s=64x64:r={fps}:d={dur}",
                "-vf", "format=gray,geq=lum='if(lt(Y,H/2),floor(N/16)*16,mod(N,16)*16+8)'",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-qp", "0")


def decode_frame_index(path):
    from PIL import Image
    im = Image.open(path).convert("L")
    w, h = im.size
    top = list(im.crop((0, 0, w, int(h * 0.44))).getdata())
    bot = list(im.crop((0, int(h * 0.56), w, h)).getdata())
    return round(sum(top) / len(top) / 16) * 16 + round((sum(bot) / len(bot) - 8) / 16)
