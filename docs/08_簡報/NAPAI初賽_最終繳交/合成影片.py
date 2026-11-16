"""NAPAI 初賽 Demo 影片：把組員的錄音切成 10 段 → 字幕依實際聲音對時 → 畫面＋字幕＋配音合成 MP4。

用法：
    D:\\democase\\ai\\.venv\\Scripts\\python.exe "D:\\democase\\ai\\docs\\08_簡報\\NAPAI初賽_最終繳交\\合成影片.py"

收到新錄音時，只要改下面的 SECTIONS（哪個檔案的第幾秒到第幾秒屬於哪一段）。
"""
import io
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
TOOLS = Path(r"D:\democase\ai\.tools")
FFMPEG = str(TOOLS / "ffmpeg" / "ffmpeg.exe")
FFPROBE = str(TOOLS / "ffmpeg" / "ffprobe.exe")
WHISPER_PY = str(TOOLS / "whisper" / "venv" / "Scripts" / "python.exe")
ALIGN = str(TOOLS / "whisper" / "align.py")
REC = HERE / "錄音"
SEC_DIR = REC / "分段"
MAT = HERE / "影片素材"
TMP = Path(r"D:\democase\.tmp\napai_build")
FINAL = HERE / "Agentic_AI_五專升二技備審準備AIAgent_初賽Demo.mp4"
FPS, W, H = 25, 1280, 720
LEAD = 0.2          # 每段畫面開始後 0.2 秒才開口
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 30)

# 錄音 → 段落：(段落檔名, [(原始錄音, 從第幾秒, 到第幾秒或 None＝到結尾), …])
# 2026-10-16 用語音辨識與音量最低點決定切點；組員開頭多唸的段落標題也在這裡剪掉
SECTIONS = [
    ("01_問題", [("1.m4a", 0, 15.4)]),
    ("02_Agent流程", [("1.m4a", 15.4, None), ("2.m4a", 0, 10.04)]),
    ("03_Agentic設計", [("2.m4a", 10.04, None), ("3.m4a", 0, 5.6)]),  # 5.6 秒「由人確認」說完，後面的停頓不要
    ("04_管理員Agent", [("3.m4a", 6.93, None), ("4.m4a", 0, None), ("5.m4a", 0, None)]),
    ("05_學生首頁", [("6.m4a", 0, None), ("7.m4a", 0, None)]),
    ("06_目標校系", [("目標校系.m4a", 1.83, None)]),
    ("07_缺件比對", [("缺件比對.m4a", 1.39, None)]),
    ("08_一鍵補件", [("一鍵補件.m4a", 1.81, None)]),
    ("09_自傳", [("自傳.m4a", 1.11, None)]),
    ("10_導師端", [("導師端.m4a", 1.22, None)]),
]

# 畫面：(素材, 原始畫面從第幾秒, 到第幾秒, 旁白原稿)；素材 = 圖片檔名、"admin" 或 "op"
CLIPS = [
    ("01_問題.png", 0, 15, "五專生準備二技備審，常常到最後才發現資料散在各處，也不知道目標校系到底還缺什麼。我們問過的畢業學長姐，四個人都說需要重做或重新找資料。"),
    ("02_Agent任務流程.png", 0, 15, "所以我們做了一個備審準備 Agent。它把「準備某個校系」拆成五步：選目標、找規則、比對證據、排待辦、交給老師覆核。"),
    ("03_Agentic設計.png", 0, 15, "它會查詢資料、比對官方的評分比重、建立待辦；資料補上後狀態會改變。最重要的是，AI 不替學生做決定，正式判斷一定由人確認。"),
    ("admin", 0, 44, "首先是 Agent 找規則。管理員上傳官方簡章後，系統計算檔案雜湊、和上一版比對，有變更才建立更新紀錄，每次執行都留下紀錄。下一步的 AI 擷取加權會呼叫 Gemini；展示版沒有設定金鑰，所以由管理員在校系資料頁逐項核對加權，確認後才核准給學生使用。"),
    # 「畫面都是測試用的假資料」組員沒錄到，改用操作畫面右上角的固定標籤說明
    ("op", 0, 13, "這是學生首頁。五年的路線用一條路表示，學生知道自己在哪個階段。"),
    ("op", 19.7, 31, "學生選想考的校系，卡片會顯示官方簡章的評分項目和比重。"),
    ("op", 36.5, 86, "系統比對學生已確認的資料。方塊越寬，佔分越多；裝得越滿，準備越完整。這位同學準備度九成三。點開還差一點的「其他」，會列出缺活動和幹部經歷。往下是依佔分排序的備審目錄，右邊是導師確認狀態，和產出備審 Word 前還沒完成的事。"),
    ("op", 95.1, 105.8, "點「去新增」就到新增頁；補上並確認後，準備度會重新計算。"),
    ("op", 105.8, 128, "自傳只引用學生確認過的資料，每段都標出用了哪些證據，學生要自己改成自己的話。"),
    ("op", 137.4, 179, "導師可以看到學生送出的版本、各評分項目的狀態和當時送出的資料，學生之後修改也不會改到已送出的版本。我們的設計是 AI 負責整理和提醒，學生和導師負責判斷。AI 擷取加權、疑義自動轉給導師，是接下來要完成的部分。謝謝。"),
]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def duration(path):
    return float(run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                     capture_output=True, text=True).stdout.strip())


# ---------- 1. 錄音切成 10 段 ----------
SEC_DIR.mkdir(exist_ok=True)
audio_len = {}
for idx, (name, parts) in enumerate(SECTIONS):
    out = SEC_DIR / f"{name}.wav"
    if not all((REC / p[0]).exists() for p in parts):
        print(f"{name}：錄音還沒到齊，略過")
        out.unlink(missing_ok=True)
        continue
    cmd, chains = [FFMPEG, "-y", "-v", "error"], []
    for i, (fname, a, b) in enumerate(parts):
        cmd += ["-i", str(REC / fname)]
        trim = f"atrim=start={a}" + (f":end={b}" if b is not None else "")
        chains.append(f"[{i}:a]{trim},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[p{i}]")
    joined = "".join(f"[p{i}]" for i in range(len(parts)))
    strip = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05"
    chains.append(f"{joined}concat=n={len(parts)}:v=0:a=1,{strip},areverse,{strip},areverse,"
                  "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[out]")
    run(cmd + ["-filter_complex", ";".join(chains), "-map", "[out]", "-c:a", "pcm_s16le", str(out)])
    audio_len[idx] = duration(out)
    print(f"{name}：{audio_len[idx]:.1f} 秒（畫面原本 {CLIPS[idx][2] - CLIPS[idx][1]:.1f} 秒）")

# ---------- 2. 字幕依實際聲音對時 ----------
TMP.mkdir(parents=True, exist_ok=True)
(TMP / "clip_text.json").write_text(json.dumps([c[3] for c in CLIPS], ensure_ascii=False), encoding="utf-8")
cues_json = TMP / "cues.json"
run([WHISPER_PY, "-X", "utf8", ALIGN, str(cues_json), str(TMP / "clip_text.json"), str(SEC_DIR)],
    stderr=subprocess.DEVNULL)
ALIGNED = {int(k): v for k, v in json.loads(cues_json.read_text(encoding="utf-8")).items()}

# ---------- 3. 畫面：每段長度 = 原本長度，聲音比較長時延長 ----------
for src, folder, ss, t in (("系統操作畫面_無聲_3分鐘.webm", "op", 4.1, 180), ("管理員Agent畫面_無聲.webm", "admin", 2.0, 46)):
    d = TMP / folder
    if not d.exists() or len(list(d.glob("*.png"))) < 10:
        d.mkdir(exist_ok=True)
        run([FFMPEG, "-y", "-v", "error", "-ss", str(ss), "-i", str(MAT / src), "-t", str(t), str(d / "%05d.png")])
frames = {k: sorted((TMP / k).glob("*.png")) for k in ("op", "admin")}


def split_sentences(text):
    out = []
    for p in [p for p in re.split(r"(?<=[。！？；])", text) if p.strip()]:
        while len(p) > 34:
            cut = max(p.rfind("，", 0, 34), p.rfind("、", 0, 34))
            cut = cut + 1 if cut > 8 else 30
            out.append(p[:cut]); p = p[cut:]
        if p.strip():
            out.append(p)
    return out


def wrap(text):
    lines, line = [], ""
    for ch in text:
        line += ch
        if FONT.getlength(line) > 34 * 30:
            lines.append(line[:-1]); line = ch
    return lines + ([line] if line else [])


def caption(img, text):
    d = ImageDraw.Draw(img, "RGBA")
    lines = wrap(text)
    lh, box_h = 42, 42 * len(lines) + 24
    top = H - box_h - 28
    left = (W - max(FONT.getlength(l) for l in lines)) / 2 - 24
    d.rounded_rectangle([left, top, W - left, top + box_h], radius=10, fill=(0, 0, 0, 170))
    for i, l in enumerate(lines):
        d.text(((W - FONT.getlength(l)) / 2, top + 12 + i * lh), l, font=FONT, fill=(255, 255, 255))
    return img


BADGE_FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 20)


def badge(img):
    """操作畫面右上角固定標示：展示畫面使用測試資料。"""
    d = ImageDraw.Draw(img, "RGBA")
    text = "展示畫面：測試資料"
    w = BADGE_FONT.getlength(text)
    d.rounded_rectangle([W - w - 40, 14, W - 14, 50], radius=8, fill=(20, 30, 50, 200))
    d.text((W - w - 27, 19), text, font=BADGE_FONT, fill=(255, 255, 255))
    return img


slides, timeline, all_cues = {}, [], []
mjpg = TMP / "video.mjpg"
t0 = 0.0
with open(mjpg, "wb") as sink:
    for ci, (src, a, b, text) in enumerate(CLIPS):
        base = b - a
        if ci in ALIGNED:
            cues = [(LEAD + x, LEAD + y, s) for x, y, s in ALIGNED[ci]]
            # 畫面長度配合錄音：說完約 0.5 秒就換下一段，不留空白；操作畫面用加快播放塞進這段時間
            dur = max(cues[-1][1] + 0.3, LEAD + audio_len.get(ci, 0) + 0.5)
            if ci == len(CLIPS) - 1:  # 最後一段說完「謝謝」多停 1.5 秒收尾
                dur = max(cues[-1][1], LEAD + audio_len.get(ci, 0)) + 1.5
        else:
            sents = split_sentences(text)
            total = sum(len(s) for s in sents)
            cues, t = [], 0.0
            for s in sents:
                d = base * len(s) / total
                cues.append((t, t + d, s.strip())); t += d
            dur = base
        timeline.append((ci, t0, dur))
        all_cues += [(t0 + x, t0 + y, s) for x, y, s in cues]
        for k in range(int(round(dur * FPS))):
            lt = k / FPS
            if src.endswith(".png"):
                if src not in slides:
                    slides[src] = Image.open(MAT / src).convert("RGB").resize((W, H), Image.LANCZOS)
                img = slides[src].copy()
            else:
                fr = frames[src]
                speed = base / dur  # 大於 1 表示加快播放，整段操作仍完整呈現
                img = Image.open(fr[min(int(round((a + min(lt * speed, base)) * FPS)), len(fr) - 1)]).convert("RGB")
                img = badge(img)
            cue = next((c for c in cues if c[0] <= lt < c[1]), None)
            if cue:
                img = caption(img, cue[2])
            buf = io.BytesIO(); img.save(buf, "JPEG", quality=90); sink.write(buf.getvalue())
        t0 += dur
total = t0


def fmt(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


(MAT / "字幕.srt").write_text("\n".join(f"{i}\n{fmt(x)} --> {fmt(y)}\n{s}\n" for i, (x, y, s) in enumerate(all_cues, 1)),
                            encoding="utf-8")

# ---------- 4. 畫面＋配音合成 MP4 ----------
missing = [SECTIONS[i][0] for i in range(len(SECTIONS)) if i not in audio_len]
out = FINAL if not missing else HERE / f"預覽_缺{len(missing)}段_{FINAL.name}"
cmd = [FFMPEG, "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", str(mjpg)]
filters, labels = [f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.2f}[base]"], ["[base]"]
for n, (ci, start, _) in enumerate(t for t in timeline if t[0] in audio_len):
    cmd += ["-i", str(SEC_DIR / f"{SECTIONS[ci][0]}.wav")]
    ms = int(round((start + LEAD) * 1000))
    filters.append(f"[{n + 1}:a]aformat=sample_fmts=fltp:channel_layouts=stereo,adelay={ms}|{ms}[a{n}]")
    labels.append(f"[a{n}]")
filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0:dropout_transition=0[aout]")
run(cmd + ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)])
mjpg.unlink()
print(f"\n完成：{out.name}（{duration(out):.1f} 秒）")
if missing:
    print("還缺：", "、".join(missing))
for ci, start, dur in timeline:
    print(f"  {start:6.1f}–{start + dur:6.1f}  {SECTIONS[ci][0]}")
