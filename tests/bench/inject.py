"""第二轮用例的注入工具：图片 / 视频 / 音频的纯函数变换，每种都配一个可程序核验的测量函数（见 test_inject.py）。

视频叠字一律先用 PIL 画成 PNG 再 overlay，不用 ffmpeg drawtext（中文路径和字体问题）。
"""
import colorsys
import os
import random
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageStat

from common import ROOT

from video_review import ffmpeg_exe, probe_video  # noqa: E402

FONT_R = str(ROOT / "assets_lib" / "NotoSansSC-Regular.otf")
FONT_B = str(ROOT / "assets_lib" / "NotoSansSC-Bold.otf")


# ---------------- 图片 ----------------

def font(size, bold=True):
    from PIL import ImageFont
    return ImageFont.truetype(FONT_B if bold else FONT_R, int(size))


def gray_like(im):
    """同尺寸纯灰图（b9 盲图）。"""
    return Image.new("RGB", im.size, (128, 128, 128))


def blur(im, sigma):
    return im.convert("RGB").filter(ImageFilter.GaussianBlur(sigma))


def jpeg(im, quality):
    import io
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def exposure(im, stops):
    """曝光增减（档）：亮度乘 2^stops，超出部分截断。"""
    return ImageEnhance.Brightness(im.convert("RGB")).enhance(2 ** stops)


def color_cast(im, gains=(1.0, 0.85, 0.6)):
    """白平衡错误：各通道乘不同增益（默认偏黄橙）。"""
    r, g, b = im.convert("RGB").split()
    return Image.merge("RGB", [c.point(lambda v, k=k: min(255, int(v * k))) for c, k in zip((r, g, b), gains)])


def hue_shift(im, deg):
    h, s, v = im.convert("RGB").convert("HSV").split()
    off = int(round(deg / 360 * 256))
    h = h.point(lambda x: (x + off) % 256)
    return Image.merge("HSV", (h, s, v)).convert("RGB")


def tilt(im, deg):
    """画面倾斜：旋转后裁中心再放回原尺寸，没有黑边。"""
    w, h = im.size
    r = im.convert("RGB").rotate(deg, resample=Image.BICUBIC, expand=False)
    k = 0.82
    box = (int(w * (1 - k) / 2), int(h * (1 - k) / 2), int(w * (1 + k) / 2), int(h * (1 + k) / 2))
    return r.crop(box).resize((w, h), Image.BICUBIC)


def cut_subject(im, frac=0.45, fill=(236, 238, 242)):
    """构图失误：画面左侧 frac 被裁掉，剩余部分贴在左边，右侧留空。"""
    w, h = im.size
    part = im.convert("RGB").crop((int(w * frac), 0, w, h))
    out = Image.new("RGB", (w, h), fill)
    out.paste(part, (0, 0))
    return out


def occlude(im, frac=0.38, seed=0):
    """前景遮挡：画面中部一块不透明色块。"""
    w, h = im.size
    out = im.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    rnd = random.Random(seed)
    cw, ch = int(w * frac), int(h * frac)
    x, y = (w - cw) // 2 + rnd.randint(-w // 20, w // 20), (h - ch) // 2 + rnd.randint(-h // 20, h // 20)
    d.rounded_rectangle([x, y, x + cw, y + ch], radius=min(cw, ch) // 6, fill=(70, 62, 55))
    return out


def clutter(im, n=40, seed=0):
    """背景杂乱：叠加大量半透明无关色块与线条。"""
    w, h = im.size
    base = im.convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rnd = random.Random(seed)
    for _ in range(n):
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        s = rnd.randint(min(w, h) // 30, min(w, h) // 8)
        col = (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(110, 200))
        if rnd.random() < 0.5:
            d.rectangle([x, y, x + s, y + s // 2], fill=col)
        else:
            d.line([x, y, x + rnd.randint(-s * 3, s * 3), y + rnd.randint(-s * 3, s * 3)], fill=col, width=max(2, s // 8))
    return Image.alpha_composite(base, layer).convert("RGB")


def overlay_text(im, text, xy=None, size=None, fill=(255, 255, 255), stroke=(0, 0, 0), anchor="mm", bold=True, alpha=255):
    """叠字。xy 缺省为画面中心；size 缺省为短边的 1/12。"""
    w, h = im.size
    size = size or min(w, h) / 12
    base = im.convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    xy = xy or (w / 2, h / 2)
    d.text(xy, text, font=font(size, bold), fill=(*fill, alpha), anchor=anchor,
           stroke_width=max(1, int(size / 14)) if stroke else 0, stroke_fill=(*stroke, alpha) if stroke else None)
    return Image.alpha_composite(base, layer).convert("RGB")


def low_contrast_text(im, text):
    """文字与背景对比度不足：取文字区域的平均色，文字只比背景亮一点。"""
    w, h = im.size
    box = (int(w * 0.1), int(h * 0.42), int(w * 0.9), int(h * 0.58))
    m = ImageStat.Stat(im.convert("RGB").crop(box)).mean
    col = tuple(min(255, int(c + 18)) for c in m)
    return overlay_text(im, text, size=min(w, h) / 9, fill=col, stroke=None)


def watermark(im, text, alpha=90):
    """平铺半透明水印（第三方图库 / 其他平台）。"""
    w, h = im.size
    base = im.convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = font(min(w, h) / 16)
    step_x, step_y = int(w / 2.5), int(h / 5)
    for y in range(0, h, step_y):
        for x in range(-step_x // 2 if (y // step_y) % 2 else 0, w, step_x):
            d.text((x, y), text, font=f, fill=(255, 255, 255, alpha))
    return Image.alpha_composite(base, layer).convert("RGB")


def qr_like(size=360, seed=0, caption=None):
    """二维码样式图块（定位角 + 随机模块），只用于"站外引流"视觉，不可扫。"""
    rnd = random.Random(seed)
    n = 29
    cell = size // n
    im = Image.new("RGB", (cell * n + 2 * cell, cell * n + 2 * cell + (cell * 5 if caption else 0)), (255, 255, 255))
    d = ImageDraw.Draw(im)
    o = cell

    def finder(x, y):
        d.rectangle([o + x * cell, o + y * cell, o + (x + 7) * cell - 1, o + (y + 7) * cell - 1], fill=0)
        d.rectangle([o + (x + 1) * cell, o + (y + 1) * cell, o + (x + 6) * cell - 1, o + (y + 6) * cell - 1], fill=(255, 255, 255))
        d.rectangle([o + (x + 2) * cell, o + (y + 2) * cell, o + (x + 5) * cell - 1, o + (y + 5) * cell - 1], fill=0)

    for i in range(n):
        for j in range(n):
            in_finder = (i < 8 and j < 8) or (i > n - 9 and j < 8) or (i < 8 and j > n - 9)
            if not in_finder and rnd.random() < 0.5:
                d.rectangle([o + i * cell, o + j * cell, o + (i + 1) * cell - 1, o + (j + 1) * cell - 1], fill=0)
    finder(0, 0), finder(n - 7, 0), finder(0, n - 7)
    if caption:
        d.text((im.width / 2, cell * n + 2 * cell + cell * 2.2), caption, font=font(cell * 2.2), fill=(20, 20, 20), anchor="mm")
    return im


def paste_center(im, tile, cx=0.5, cy=0.5):
    out = im.convert("RGB").copy()
    w, h = out.size
    out.paste(tile, (int(w * cx - tile.width / 2), int(h * cy - tile.height / 2)))
    return out


# ---- 测量（自检用） ----

def mean_luma(im):
    return ImageStat.Stat(im.convert("L")).mean[0]


def mean_hue_deg(im):
    """饱和像素的平均色相（圆周平均，度）。"""
    import math
    small = im.convert("RGB").resize((64, 64))
    sx = sy = 0.0
    for r, g, b in small.getdata():
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > 0.25 and v > 0.2:
            sx += math.cos(2 * math.pi * h) * s
            sy += math.sin(2 * math.pi * h) * s
    return (math.degrees(math.atan2(sy, sx)) + 360) % 360


def sharpness(im):
    """拉普拉斯近似的边缘能量：越大越清晰。"""
    e = im.convert("L").filter(ImageFilter.FIND_EDGES)
    return ImageStat.Stat(e).var[0]


def diff_ratio(a, b, thresh=12):
    """两张同尺寸图里有明显差异的像素比例。"""
    d = ImageChops.difference(a.convert("L"), b.convert("L")).point(lambda v: 255 if v > thresh else 0)
    return ImageStat.Stat(d).mean[0] / 255


# ---------------- 视频 ----------------

def ffmpeg(*args):
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
                       capture_output=True, text=True, errors="replace")
    if p.returncode:
        raise RuntimeError(f"ffmpeg 失败：{p.stderr[-800:]}")


def frame_times(duration, n=12):
    """与 video_review.extract_frames 相同的抽帧时间点（test_inject 里对照产品实现）。"""
    times = [t / 2 for t in range(0, 6) if t / 2 < duration]
    if duration > 3:
        step = (duration - 3) / n
        times += [round(3 + step * (i + 0.5), 2) for i in range(n)]
    times.append(max(duration - 0.1, 0))
    return sorted(set(times))


def between_frames(duration, near, n=12):
    """near 附近两个相邻抽帧点的正中间，以及两点间距。"""
    ts = frame_times(duration, n)
    pairs = [(a, b) for a, b in zip(ts, ts[1:]) if b - a >= 0.9]  # 0.5 秒字卡两侧各留 ≥0.2 秒
    a, b = min(pairs, key=lambda p: abs((p[0] + p[1]) / 2 - near))
    return (a + b) / 2, b - a


def duration_of(path):
    return probe_video(path).get("时长(秒)")


def video_size(path):
    w, h = probe_video(path)["分辨率"].split("x")
    return int(w), int(h)


def vf(src, dst, filt, extra=()):
    """只改画面：-vf 滤镜链，音频流复制。"""
    ffmpeg("-i", src, "-vf", filt, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "copy", *extra, dst)


def overlay_png(src, dst, png, t0, t1):
    """在 [t0, t1] 区间把 png（与视频同尺寸、可带透明）盖到画面上。"""
    ffmpeg("-i", src, "-loop", "1", "-i", png, "-filter_complex",
           f"[1:v]format=rgba[o];[0:v][o]overlay=0:0:enable='between(t,{t0:.3f},{t1:.3f})':shortest=1,format=yuv420p[v]",
           "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", dst)


def card_png(size, text, sub=None, bg=(20, 20, 24, 235), path=None):
    """整屏字卡（违规字卡、引流字卡等）。"""
    w, h = size
    im = Image.new("RGBA", size, bg)
    d = ImageDraw.Draw(im)
    u = min(w, h)
    d.text((w / 2, h * 0.45), text, font=font(u / 9), fill=(255, 255, 255, 255), anchor="mm")
    if sub:
        d.text((w / 2, h * 0.58), sub, font=font(u / 18, False), fill=(230, 230, 230, 255), anchor="mm")
    path = path or Path(tempfile.mkstemp(suffix=".png")[1])
    im.save(path)
    return Path(path)


def corner_png(size, tile, pos="br", margin=0.04, path=None):
    """透明底，tile 贴在角落（二维码、水印角标）。"""
    w, h = size
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    m = int(min(w, h) * margin)
    x = w - tile.width - m if "r" in pos else m
    y = h - tile.height - m if "b" in pos else m
    im.paste(tile.convert("RGBA"), (x, y))
    path = path or Path(tempfile.mkstemp(suffix=".png")[1])
    im.save(path)
    return Path(path)


def shake(src, dst, amp=0.035):
    w, h = video_size(src)
    k = 1 - 2 * amp
    vf(src, dst, f"crop=iw*{k}:ih*{k}:iw*{amp}+iw*{amp}*sin(n*1.7):ih*{amp}+ih*{amp}*cos(n*2.3),scale={w}:{h},setsar=1")


def underexpose(src, dst, brightness=-0.22):
    vf(src, dst, f"eq=brightness={brightness}:contrast=0.85")


# 基准片靠逐帧噪点躲开 freezedetect；模糊、低码率会把噪点抹平，技术参数里凭空多出冻结帧（再命中 R5），所以事后补回噪点
def vblur(src, dst, sigma=6):
    vf(src, dst, f"gblur=sigma={sigma},noise=alls=10:allf=t")


def lowbitrate(src, dst, kbps=60):
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    tmp = Path(tmp)
    try:
        ffmpeg("-i", src, "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k",
               "-bufsize", f"{kbps}k", "-pix_fmt", "yuv420p", "-c:a", "copy", tmp)
        vf(tmp, dst, "noise=alls=6:allf=t")
    finally:
        tmp.unlink(missing_ok=True)


def platform_box(src, dst, w, h):
    """竖屏片塞进横屏画布（左右黑边），用于平台反转对照。"""
    vf(src, dst, f"scale=-2:{h},pad={w}:{h}:(ow-iw)/2:0:black,setsar=1")


# ---------------- 音频 ----------------

def tts_wav(text, out):
    """Windows 自带语音合成（Microsoft Huihui，zh-CN）。参数走环境变量，避免拼命令串。"""
    env = {**os.environ, "VR_TTS_TEXT": text, "VR_TTS_OUT": str(out)}
    ps = ("Add-Type -AssemblyName System.Speech;"
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          "try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female, "
          "[System.Speech.Synthesis.VoiceAge]::Adult, 0, [System.Globalization.CultureInfo]'zh-CN') } catch {};"
          "$s.SetOutputToWaveFile($env:VR_TTS_OUT); $s.Speak($env:VR_TTS_TEXT); $s.Dispose()")
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, capture_output=True, text=True,
                       errors="replace")
    if p.returncode or not Path(out).exists() or Path(out).stat().st_size < 2000:
        raise RuntimeError(f"语音合成失败：{p.stderr[-400:]}")
    return Path(out)


def mix_voice(src, dst, wav, at, gain_db=4):
    """在 at 秒处把人声混进原音轨（原音轨压低 8dB 让人声听得清），再整体响度归一到 -15 LUFS（与基准一致，免得 V4 因响度变化降分）。"""
    ms = int(at * 1000)
    ffmpeg("-i", src, "-i", wav, "-filter_complex",
           f"[0:a]volume=-8dB[a0];[1:a]adelay={ms}|{ms},volume={gain_db}dB,apad[a1];[a0][a1]amix=inputs=2:duration=first:normalize=0,"
           f"loudnorm=I=-15:TP=-1.5:LRA=11,aresample=48000[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", dst)


def gain(src, dst, db):
    """整体音量增减 db（响度梯度），画面复制。"""
    ffmpeg("-i", src, "-af", f"volume={db}dB", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", dst)


def shift_audio(src, dst, seconds):
    """音轨整体延后 seconds 秒（音画不同步）。"""
    ms = int(seconds * 1000)
    ffmpeg("-i", src, "-af", f"adelay={ms}|{ms}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", dst)


def blackdetect(path):
    return probe_video(path).get("黑帧区间", [])


def parse_interval(s):
    a, b = re.findall(r"[\d.]+", s)[:2]
    return float(a), float(b)
