"""Windows(DirectShow) 장치 목록에서 웹캠·마이크를 골라 수집 프로그램용 FFmpeg 입력 JSON을 만든다.

    python -m scripts.make_capture_input                      # 자동 선택, artifacts/demo/capture-input.json 저장
    python -m scripts.make_capture_input --list               # 장치 목록만 보기
    python -m scripts.make_capture_input --audio "G435"       # 이름에 'G435'가 들어간 마이크 선택

자동 선택은 영상은 첫 번째 카메라(가상 카메라 제외), 소리는 '마이크 배열/Microphone Array'를 우선하고 없으면
첫 번째 마이크다. 선택 결과는 항상 출력하므로 잘못 골랐으면 --video/--audio로 지정한다.
FFmpeg는 PATH의 ffmpeg, 환경변수 FFMPEG, imageio-ffmpeg 순서로 찾는다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEVICE_LINE = re.compile(r'"(?P<name>[^"]+)"\s+\((?P<kind>video|audio|none)\)')
VIRTUAL = re.compile(r"virtual|obs|ndi|snap camera|manycam", re.IGNORECASE)
PREFERRED_MIC = re.compile(r"마이크 배열|microphone array|array", re.IGNORECASE)
MODE_LINE = re.compile(r"(?:(?P<key>vcodec|pixel_format)=(?P<fmt>\w+))\s+min s=(?P<w>\d+)x(?P<h>\d+) fps=(?P<minfps>[\d.]+)\s+max s=\d+x\d+ fps=(?P<fps>[\d.]+)")
WANT_FPS = 30
AUDIO_BUFFER_MS = 50
PREVIEW_WIDTH_MAX = 640


def parse_devices(text: str) -> dict[str, list[str]]:
    """`ffmpeg -list_devices true -f dshow -i dummy` 출력에서 장치 이름을 뽑는다."""
    devices: dict[str, list[str]] = {"video": [], "audio": []}
    for line in text.splitlines():
        m = DEVICE_LINE.search(line)
        if m and m["kind"] in devices and m["name"] not in devices[m["kind"]]:
            devices[m["kind"]].append(m["name"])
    return devices


def choose(devices: dict[str, list[str]], video: str | None = None, audio: str | None = None) -> tuple[str, str]:
    def pick(kind: str, wanted: str | None, prefer: re.Pattern | None, skip: re.Pattern | None) -> str:
        names = devices[kind]
        if wanted:
            hits = [n for n in names if wanted.lower() in n.lower()]
            if not hits:
                raise SystemExit(f"'{wanted}'이(가) 들어간 {kind} 장치가 없습니다. 목록: {names}")
            return hits[0]
        if skip:
            names = [n for n in names if not skip.search(n)]
        if prefer:
            preferred = [n for n in names if prefer.search(n)]
            names = preferred or names
        if not names:
            raise SystemExit(f"사용할 수 있는 {kind} 장치가 없습니다. 장치 연결과 Windows 개인정보 설정(카메라·마이크)을 확인하세요.")
        return names[0]

    return pick("video", video, None, VIRTUAL), pick("audio", audio, PREFERRED_MIC, None)


def parse_modes(text: str) -> list[dict]:
    """`ffmpeg -f dshow -list_options true -i video=...` 출력에서 (형식, 해상도, 최대 fps) 목록을 뽑는다."""
    modes = []
    for line in text.splitlines():
        m = MODE_LINE.search(line)
        if m:
            modes.append({"kind": m["key"], "format": m["fmt"], "width": int(m["w"]), "height": int(m["h"]), "fps": float(m["fps"])})
    return modes


def choose_mode(modes: list[dict], want_fps: float = WANT_FPS, max_width: int = PREVIEW_WIDTH_MAX) -> dict | None:
    """원하는 fps를 낼 수 있는 모드 중 640px 이하에서 가장 큰 해상도를 고른다. MJPEG를 우선한다(USB 대역폭이 작다).
    없으면 fps가 가장 높은 모드를 고른다. 조회가 안 되면 None(옵션 없이 기본값으로 연다)."""
    if not modes:
        return None
    ok = [m for m in modes if m["fps"] >= want_fps and m["width"] <= max_width]
    if ok:
        return max(ok, key=lambda m: (m["width"] * m["height"], m["format"] == "mjpeg"))
    return max(modes, key=lambda m: (min(m["fps"], want_fps), -m["width"]))


def mode_args(mode: dict | None) -> list[str]:
    if not mode:
        return []
    fps = int(mode["fps"]) if float(mode["fps"]).is_integer() else mode["fps"]
    args = ["-video_size", f"{mode['width']}x{mode['height']}", "-framerate", str(fps)]
    args += ["-vcodec", "mjpeg"] if mode["format"] == "mjpeg" else ["-pixel_format", mode["format"]]
    return args


def build_args(video_name: str, audio_name: str, mode: dict | None = None) -> list[str]:
    # 입력 0 = 영상, 입력 1 = 소리. 수집 프로그램의 --video-map 0:v:0 --audio-map 1:a:0 과 짝이다.
    return ["-f", "dshow", "-rtbufsize", "100M", *mode_args(mode), "-i", f"video={video_name}",
            # dshow 마이크의 기본 버퍼(500ms)가 영상 프레임까지 0.5초 단위로 뭉쳐 내보내게 만든다 -> 50ms
            "-f", "dshow", "-audio_buffer_size", str(AUDIO_BUFFER_MS), "-i", f"audio={audio_name}"]


def find_ffmpeg(explicit: str | None = None) -> str:
    candidates = [explicit, os.environ.get("FFMPEG"), shutil.which("ffmpeg")]
    for c in candidates:
        if c and (Path(c).is_file() or shutil.which(c)):
            return c
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit("FFmpeg를 찾을 수 없습니다. 설치(winget install Gyan.FFmpeg)하거나 환경변수 FFMPEG에 경로를 지정하세요.")


def list_devices(ffmpeg: str) -> dict[str, list[str]]:
    out = subprocess.run([ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    return parse_devices(out.stderr + out.stdout)


def list_video_modes(ffmpeg: str, name: str) -> list[dict]:
    out = subprocess.run([ffmpeg, "-hide_banner", "-f", "dshow", "-list_options", "true", "-i", f"video={name}"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    return parse_modes(out.stderr + out.stdout)


def device_names(args: list[str]) -> tuple[str | None, str | None]:
    """입력 인수에서 (카메라 이름, 마이크 이름)을 읽는다."""
    names = {"video": None, "audio": None}
    for a in args:
        for kind in names:
            if a.startswith(kind + "="):
                names[kind] = a[len(kind) + 1:]
    return names["video"], names["audio"]


def refresh(ffmpeg: str, output: Path, video: str | None = None, audio: str | None = None) -> bool:
    """장치를 다시 찾아 입력 JSON을 갱신한다. 장치가 없으면(뽑힘 등) False를 돌려 주고 파일은 건드리지 않는다.

    수집 프로그램이 막 죽은 직후에는 카메라가 아직 점유 중이라 모드 목록을 못 읽을 수 있다. 같은 장치 조합이면
    기존 입력(해상도·fps 포함)을 그대로 두어 30fps 설정이 기본값으로 후퇴하지 않게 한다."""
    try:
        v, a = choose(list_devices(ffmpeg), video, audio)
    except (SystemExit, subprocess.SubprocessError, OSError):
        return False
    mode = choose_mode(list_video_modes(ffmpeg, v))
    old = None
    try:
        old = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    if mode is None and isinstance(old, list) and device_names(old) == (v, a):
        return True
    new = build_args(v, a, mode)
    if new != old:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(new, ensure_ascii=False), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ffmpeg")
    ap.add_argument("--video", help="카메라 이름 일부")
    ap.add_argument("--audio", help="마이크 이름 일부")
    ap.add_argument("--output", type=Path, default=Path("artifacts/demo/capture-input.json"))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-mode", action="store_true", help="해상도·fps를 지정하지 않고 장치 기본값으로 연다")
    args = ap.parse_args(argv)

    ffmpeg = find_ffmpeg(args.ffmpeg)
    devices = list_devices(ffmpeg)
    if args.list:
        print(json.dumps(devices, ensure_ascii=False, indent=2))
        return 0
    video, audio = choose(devices, args.video, args.audio)
    mode = None if args.no_mode else choose_mode(list_video_modes(ffmpeg, video))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_args(video, audio, mode), ensure_ascii=False), encoding="utf-8")
    config = args.output.with_name("capture-config.json")  # 스크립트가 한글 경로를 안전하게 읽도록 파일로도 남긴다
    config.write_text(json.dumps({"ffmpeg": ffmpeg, "video": video, "audio": audio, "input_args_file": str(args.output)}, ensure_ascii=False), encoding="utf-8")
    print(f"ffmpeg={ffmpeg}")
    print(f"video={video}")
    print(f"audio={audio}")
    print("mode=" + (f"{mode['width']}x{mode['height']} {mode['fps']:g}fps {mode['format']}" if mode else "device default (modes not readable: camera busy?)"))
    print(f"saved={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
