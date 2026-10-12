"""README의 시스템 구조를 8단계 동작 애니메이션으로 만든다.

    python scripts/build_flow_animation.py

산출물(저장소 루트):
- PetMind_동작_애니메이션.html : 재생·일시정지·이전/다음·속도 조절이 있는 단독 HTML(스크립트 사용, 외부 의존 없음)
- PetMind_동작_애니메이션.svg  : 스크립트 없이 자동 반복 재생되는 SVG(README 이미지로 삽입 가능)

내용의 근거는 README.md 0~4장이며, 구현·검증된 범위와 가상 실행·미검증 범위를 구분해 표시한다.
"""

from __future__ import annotations

import html
import json
import textwrap
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]  # 저장소 루트: 열자마자 보이도록 docs/가 아닌 최상위에 둔다
STEP_S = 6.0      # 단계당 길이(초)
PACKET_S = 1.3    # 신호 한 번 이동 시간(초)

# ---- 장면 데이터 -------------------------------------------------------------
ZONES = [
    ("pi", 24, 70, 270, 440, "집 · Raspberry Pi"),
    ("server", 330, 70, 560, 440, "PC 서버 · FastAPI + SQLite"),
    ("guardian", 926, 70, 250, 440, "보호자 · Flutter 웹 화면"),
]
# id: (x, y, w, h, 제목, 설명, 점선 여부)
NODES = {
    "cam": (48, 115, 222, 70, "카메라", "영상 · 실장비 미검증", True),
    "mic": (48, 205, 222, 70, "마이크", "소리 · 실장비 미검증", True),
    "agent": (48, 325, 222, 86, "수집 에이전트", "구간 보관 · 서버로 전송", False),
    "spk": (48, 430, 222, 70, "스피커", "가상 실행 · 물리 미연결", True),
    "audio": (360, 115, 240, 86, "소리 분석", "에너지 후보 + 음성 LSTM", False),
    "video": (630, 115, 230, 86, "사건 영상 저장", "감지 전후 각 5초 MP4", False),
    "db": (360, 235, 240, 86, "기록 DB (SQLite)", "관찰 · 의견 · 제안", False),
    "rag": (630, 235, 230, 86, "과거 기록 검색 (MCP)", "같은 반려견의 과거만", False),
    "cmd": (360, 355, 240, 86, "음악 명령 관리", "요청 → 수신 → 완료", False),
    "llm": (630, 355, 230, 86, "설명 · 제안 생성", "Gemini 또는 규칙 제공자", False),
    "view": (950, 115, 202, 86, "외출 · 귀가 화면", "원본 재생 · 의견 입력", False),
    "care": (950, 235, 202, 86, "케어 제안", "근거 ID · 승인 버튼", False),
}
# id: (path, 양방향 여부)
EDGES = {
    "cam_agent": ("M270,150 H284 V352 H272", False),
    "mic_agent": ("M270,240 H284 V352 H272", False),
    "agent_audio": ("M270,380 H318 V158 H358", False),
    "audio_video": ("M600,158 H628", False),
    "audio_db": ("M480,201 V233", False),
    "video_db": ("M745,201 V212 H540 V233", False),
    "view_db": ("M950,185 H890 V224 H580 V233", True),
    "db_rag": ("M600,278 H628", False),
    "rag_llm": ("M745,321 V353", False),
    "llm_care": ("M860,398 H900 V290 H948", False),
    "care_cmd": ("M1051,321 V480 H480 V443", False),
    "cmd_spk": ("M360,420 H330 V465 H272", True),
}
# 단계: 제목, 설명, 배지, 강조 노드, [(간선, 역방향)] 순차 신호
STEPS = [
    dict(title="1. 외출을 시작합니다",
         desc="보호자가 화면에서 외출을 시작하면 서버에 수집 요청이 만들어집니다. 집의 수집 에이전트가 서버의 요청을 확인해 가져가며, 서버와 장치의 시계 차이가 2초를 넘으면 수집을 시작하지 않습니다.",
         badge="구현됨 · 서버–장치 왕복은 가상 장치로 확인", nodes=["view", "db", "agent"], packets=[("view_db", False)]),
    dict(title="2. 소리와 영상을 모읍니다",
         desc="마이크와 카메라 입력을 약 5초 단위 구간으로 나눠 임시 보관합니다. 오래된 구간은 지워 저장 공간을 아낍니다.",
         badge="코드 구현 · 파일 입력으로 검증 / 실제 Pi 카메라·마이크는 미검증", nodes=["cam", "mic", "agent"],
         packets=[("cam_agent", False), ("mic_agent", False)]),
    dict(title="3. 소리를 분석합니다",
         desc="서버가 5초 소리를 두 가지로 봅니다. ① 소리가 크게 변했는지(에너지 후보) ② 음성 LSTM 모델이 개 짖음 소리 후보로 보는지(점수). 감정이나 질환을 판단하지 않습니다.",
         badge="구현됨 · 공개 음원 평가에서 개 소리를 놓치는 경우가 많음(재현율 28.3%)", nodes=["agent", "audio"],
         packets=[("agent_audio", False)]),
    dict(title="4. 짖음 후보면 앞뒤 장면을 저장합니다",
         desc="모델 점수가 기준을 넘으면 그 앞뒤 각 5초 영상을 저장해 관찰에 연결합니다. 카메라는 보호자가 직접 확인하는 용도이며 영상으로 행동을 자동 판단하지 않습니다.",
         badge="구현됨 · 30초 테스트 파일로 확인", nodes=["audio", "video", "db"],
         packets=[("audio_video", False), ("video_db", False)]),
    dict(title="5. 관찰을 기록합니다",
         desc="관찰 ID, 시각, 출처, 분석 결과를 반려견별로 SQLite DB에 저장합니다. 서버를 다시 시작해도 기록이 남습니다.",
         badge="구현됨", nodes=["audio", "db"], packets=[("audio_db", False)]),
    dict(title="6. 보호자가 직접 확인합니다",
         desc="화면에서 원본 소리와 영상을 재생하고 '개 짖음 소리 / TV 소리 / 잘 모르겠음' 같은 의견을 남깁니다. AI 판정과 보호자 의견은 따로 보관됩니다.",
         badge="구현됨 · 브라우저 흐름 확인", nodes=["view", "db"], packets=[("view_db", True), ("view_db", False)]),
    dict(title="7. 과거 기록을 찾아 설명합니다",
         desc="같은 반려견의 과거 기록만 검색해 Gemini 또는 규칙 제공자에게 전달합니다. 설명과 제안에는 근거가 된 기록 ID가 함께 표시되고, 호출이 실패하면 규칙 방식으로 대체합니다.",
         badge="구현됨 · 자체 질문 20개 평가, 실제 보호자 질문 평가는 아직", nodes=["db", "rag", "llm", "care"],
         packets=[("db_rag", False), ("rag_llm", False), ("llm_care", False)]),
    dict(title="8. 승인하면 음악 명령을 보냅니다",
         desc="음성 후보와 보호자의 '개 소리' 확인 의견이 함께 있을 때만 음악이 제안됩니다. 보호자가 승인하면 명령이 요청 → 수신 → 완료 순으로 진행하고, 응답이 없으면 시간 초과로 기록합니다.",
         badge="가상 실행 · 실제 스피커는 연결하지 않음", nodes=["care", "cmd", "spk"],
         packets=[("care_cmd", False), ("cmd_spk", False), ("cmd_spk", True)]),
]
STEP_NODES = [set(s["nodes"]) for s in STEPS]
GLOSSARY = [
    ("짖음 후보", "모델이 '개 짖음 소리일 수 있다'고 본 5초 구간입니다. 실제 짖음 횟수나 감정을 뜻하지 않습니다."),
    ("LSTM", "시간에 따라 변하는 소리의 특징을 읽는 인공지능 모델입니다. 여기서는 5초 소리가 개 짖음 소리 후보인지 점수를 냅니다."),
    ("RAG · MCP", "질문과 관련된 과거 기록을 먼저 찾아 AI에게 근거로 건네는 방식입니다. MCP는 그 검색 도구를 부르는 표준 방법입니다."),
    ("Gemini", "구글의 생성형 AI입니다. API 키가 없거나 호출이 실패하면 규칙 기반 제공자로 대신 설명합니다."),
    ("SQLite", "서버 PC 안의 파일 하나로 동작하는 작은 데이터베이스입니다."),
]


def lerp_intervals(intervals, total, fade=0.25):
    """[(시작, 끝)] 구간에서만 1이 되는 opacity 키프레임(values, keyTimes)을 만든다."""
    gap = 0.01  # keyTimes가 서로 겹치지 않도록 하는 최소 간격(초)
    pts: list[tuple[float, float]] = []
    for a, b in intervals:
        if a - fade > 0:
            pts.append((a - fade, 0.0))
        pts += [(a, 1.0), (b, 1.0)]
        if b + fade < total:
            pts.append((b + fade, 0.0))
    if pts[0][0] > 0:
        pts.insert(0, (0.0, 0.0))
    if pts[-1][0] < total:
        pts.append((total, 0.0))
    clean: list[tuple[float, float]] = []
    for t, v in pts:
        if clean and t < clean[-1][0] + gap:
            t = clean[-1][0] + gap
        clean.append((min(t, total), v))
    # 끝 시각이 total로 눌려 겹치면 앞 점을 버리고 마지막 점의 값을 유지한다
    while len(clean) > 1 and clean[-1][0] <= clean[-2][0]:
        clean.pop(-2)
    return ";".join(f"{v:g}" for _, v in clean), ";".join(f"{t / total:.6f}" for t, _ in clean)


def node_svg(nid, hl_attrs=""):
    x, y, w, h, title, sub, dashed = NODES[nid]
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    return (f'<g class="node" id="n-{nid}"><rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" rx="12"{dash}/>'
            f'<text class="nt" x="{x + 16}" y="{y + 30}">{html.escape(title)}</text>'
            f'<text class="ns" x="{x + 16}" y="{y + 54}">{html.escape(sub)}</text>'
            f'<rect class="hl" x="{x - 3}" y="{y - 3}" width="{w + 6}" height="{h + 6}" rx="14"{hl_attrs}/></g>')


def scene_svg(animated_svg: bool) -> str:
    total = STEP_S * len(STEPS)
    out = []
    for zid, x, y, w, h, label in ZONES:
        out.append(f'<rect class="zone" x="{x}" y="{y}" width="{w}" height="{h}" rx="18"/>'
                   f'<text class="zt" x="{x + 18}" y="{y + 28}">{html.escape(label)}</text>')
    for eid, (d, both) in EDGES.items():
        mk = ' marker-start="url(#ah)" marker-end="url(#ah)"' if both else ' marker-end="url(#ah)"'
        hl = ""
        if animated_svg:
            iv = [(i * STEP_S, (i + 1) * STEP_S) for i, s in enumerate(STEPS) if any(p[0] == eid for p in s["packets"])]
            v, k = lerp_intervals(iv, total)
            hl = f'<animate attributeName="opacity" values="{v}" keyTimes="{k}" dur="{total}s" repeatCount="indefinite"/>'
        out.append(f'<path class="edge" id="e-{eid}" d="{d}"{mk}/><path class="edge hot" d="{d}" opacity="0"{mk}>{hl}</path>')
    for nid in NODES:
        attrs = ""
        if animated_svg:
            iv = [(i * STEP_S, (i + 1) * STEP_S) for i, ns in enumerate(STEP_NODES) if nid in ns]
            v, k = lerp_intervals(iv, total)
            out.append(node_svg(nid).replace('opacity="0"', "").replace('class="hl"', f'class="hl" opacity="0"').replace(
                "/></g>", f'><animate attributeName="opacity" values="{v}" keyTimes="{k}" dur="{total}s" repeatCount="indefinite"/></rect></g>'))
        else:
            out.append(node_svg(nid))
    if animated_svg:
        for i, s in enumerate(STEPS):
            t = i * STEP_S
            for j, (eid, rev) in enumerate(s["packets"]):
                a = t + 0.4 + j * (PACKET_S + 0.15)
                b = a + PACKET_S
                v, k = lerp_intervals([(a, b)], total, fade=0.05)
                kp = "1;1;0;0" if rev else "0;0;1;1"
                kt = f"0;{a / total:.5f};{b / total:.5f};1"
                out.append(f'<circle class="pk" r="8" opacity="0"><animate attributeName="opacity" values="{v}" keyTimes="{k}" dur="{total}s" repeatCount="indefinite"/>'
                           f'<animateMotion dur="{total}s" repeatCount="indefinite" path="{EDGES[eid][0]}" keyPoints="{kp}" keyTimes="{kt}" calcMode="linear"/></circle>')
    return "\n".join(out)


STYLE_COMMON = """
:root{--bg:#f6f7fb;--zone:#eceef6;--zl:#cfd3e6;--node:#fff;--line:#8d93ad;--tx:#1d2033;--mu:#5b607a;--ac:#5b4bd6;--ok:#16a34a;--hot:#5b4bd6;--cap:#ffffff}
@media (prefers-color-scheme:dark){:root{--bg:#12141c;--zone:#1b1e2b;--zl:#2c3044;--node:#232738;--line:#6b7190;--tx:#eceef8;--mu:#a2a8c4;--ac:#9b8cff;--ok:#4ade80;--hot:#9b8cff;--cap:#1b1e2b}}
"""
STYLE_SVG = """
.zone{fill:var(--zone);stroke:var(--zl)}.zt{fill:var(--mu);font:700 15px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
.box{fill:var(--node);stroke:var(--line);stroke-width:1.6}.nt{fill:var(--tx);font:700 18px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
.ns{fill:var(--mu);font:13.5px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}.hl{fill:none;stroke:var(--hot);stroke-width:3.5;opacity:0}
.edge{fill:none;stroke:var(--line);stroke-width:2.2}.edge.hot{stroke:var(--hot);stroke-width:3.4}.pk{fill:var(--ok);stroke:var(--bg);stroke-width:2}
.ah{fill:var(--line)}.cap{fill:var(--tx);font:700 21px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}.cd{fill:var(--tx);font:16px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
.cb{fill:var(--ac);font:700 14px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}.lg{fill:var(--mu);font:13px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
"""
DEFS = ('<defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
        '<path class="ah" d="M0,0 L10,5 L0,10 z"/></marker></defs>')


def legend(y):
    return (f'<rect class="box" x="30" y="{y - 11}" width="26" height="14" rx="4"/><text class="lg" x="64" y="{y}">구현·검증한 흐름</text>'
            f'<rect class="box" x="190" y="{y - 11}" width="26" height="14" rx="4" stroke-dasharray="5 3"/><text class="lg" x="224" y="{y}">가상 실행 또는 실장비 미검증</text>'
            f'<circle class="pk" cx="446" cy="{y - 4}" r="6"/><text class="lg" x="460" y="{y}">신호(데이터·명령)가 이동하는 모습</text>')


def build_svg() -> str:
    total = STEP_S * len(STEPS)
    cap = []
    for i, s in enumerate(STEPS):
        v, k = lerp_intervals([(i * STEP_S + 0.05, (i + 1) * STEP_S - 0.05)], total, fade=0.2)
        lines = textwrap.wrap(s["desc"], width=62)
        body = "".join(f'<text class="cd" x="40" y="{624 + 26 * n}">{html.escape(l)}</text>' for n, l in enumerate(lines))
        cap.append(f'<g opacity="0"><animate attributeName="opacity" values="{v}" keyTimes="{k}" dur="{total}s" repeatCount="indefinite"/>'
                   f'<text class="cap" x="40" y="566">{html.escape(s["title"])}</text>'
                   f'<text class="cb" x="40" y="590">{html.escape(s["badge"])}</text>{body}</g>')
    dots = []
    for i in range(len(STEPS)):
        v, k = lerp_intervals([(i * STEP_S, (i + 1) * STEP_S)], total, fade=0.2)
        dots.append(f'<circle cx="{1000 + i * 24}" cy="552" r="6" fill="var(--zl)"/><circle cx="{1000 + i * 24}" cy="552" r="6" fill="var(--ac)" opacity="0">'
                    f'<animate attributeName="opacity" values="{v}" keyTimes="{k}" dur="{total}s" repeatCount="indefinite"/></circle>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 720" width="1200" height="720" role="img" '
            f'aria-label="PetMind 동작 흐름 애니메이션: 외출 시작부터 음악 명령까지 8단계">\n<style>{STYLE_COMMON}{STYLE_SVG}</style>{DEFS}\n'
            f'<rect width="1200" height="720" fill="var(--bg)"/>\n'
            f'<text class="cap" x="24" y="40">PetMind 동작 애니메이션</text>'
            f'<text class="lg" x="24" y="60">반려견 소리 기록 → 보호자 확인 → 과거 기록 기반 설명 · 8단계가 반복 재생됩니다</text>\n'
            f'{scene_svg(True)}\n{"".join(dots)}\n{"".join(cap)}\n{legend(700)}</svg>\n')


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PetMind 동작 애니메이션</title>
<style>
__COMMON__
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.6 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',system-ui,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:26px;margin:0 0 4px}.lead{color:var(--mu);margin:0 0 16px}
.stage{background:var(--zone);border:1px solid var(--zl);border-radius:16px;padding:8px}
svg{width:100%;height:auto;display:block}
__SVGSTYLE__
.node .hl{transition:opacity .25s}.node.on .hl{opacity:1}.edge.hot{opacity:0;transition:opacity .25s}.edge.hot.on{opacity:1}
.node.dim{opacity:.55}.node{transition:opacity .25s}
.panel{margin-top:14px;background:var(--cap);border:1px solid var(--zl);border-radius:14px;padding:16px 18px}
.panel h2{margin:0 0 4px;font-size:21px}.badge{display:inline-block;color:var(--ac);font-weight:700;font-size:14px;margin-bottom:6px}
.panel p{margin:0}
.ctrl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:12px}
button{font:inherit;color:var(--tx);background:var(--cap);border:1px solid var(--zl);border-radius:10px;padding:6px 14px;cursor:pointer}
button:hover{border-color:var(--ac)}button:focus-visible{outline:3px solid var(--ac);outline-offset:2px}
button.primary{background:var(--ac);border-color:var(--ac);color:#fff}
.dots{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}
.dot{width:34px;height:34px;padding:0;border-radius:50%;font-size:14px}.dot.cur{background:var(--ac);color:#fff;border-color:var(--ac)}
select{font:inherit;color:var(--tx);background:var(--cap);border:1px solid var(--zl);border-radius:10px;padding:5px 8px}
details{margin-top:18px;background:var(--cap);border:1px solid var(--zl);border-radius:14px;padding:10px 18px}summary{cursor:pointer;font-weight:700}
dt{font-weight:700;margin-top:8px}dd{margin:0;color:var(--mu)}
.note{color:var(--mu);font-size:14px;margin-top:14px}
@media (max-width:640px){.dots{margin-left:0}.panel h2{font-size:18px}}
</style>
</head>
<body>
<div class="wrap">
<h1>PetMind 동작 애니메이션</h1>
<p class="lead">반려견 소리를 기록하고, 보호자가 확인하고, 과거 기록으로 설명하는 흐름을 8단계로 보여줍니다. 처음이라면 ▶ 재생을 누르고 아래 설명을 따라가 보세요.</p>
<div class="stage"><svg viewBox="0 54 1200 470" role="img" aria-label="PetMind 시스템 블록도">__DEFS____SCENE__</svg></div>
<div class="panel" aria-live="polite"><div class="badge" id="badge"></div><h2 id="title"></h2><p id="desc"></p></div>
<div class="ctrl">
<button id="prev" aria-label="이전 단계">◀ 이전</button>
<button id="play" class="primary" aria-label="재생 또는 일시정지">⏸ 일시정지</button>
<button id="next" aria-label="다음 단계">다음 ▶</button>
<label>속도 <select id="speed"><option value="0.6">느리게</option><option value="1" selected>보통</option><option value="1.6">빠르게</option></select></label>
<div class="dots" id="dots"></div>
</div>
<p class="note">범례: 실선 상자는 구현·검증한 부분, 점선 상자는 가상 실행이거나 실장비 미검증인 부분입니다. 초록 점은 데이터·명령이 이동하는 모습입니다. 키보드 ← → 로 단계를 넘기고 Space로 재생/정지합니다.</p>
<details><summary>용어 설명</summary><dl>__GLOSSARY__</dl></details>
<p class="note">근거: 저장소 README.md 0~4장. 이 애니메이션은 시스템의 동작 구조를 설명하는 자료이며 모델 정확도나 실제 가정 환경의 성능을 보증하지 않습니다.</p>
</div>
<script>
const STEPS=__STEPS__;
const EDGE_LEN={};
const STEP_MS=__STEPMS__, PK_MS=__PKMS__;
const svg=document.querySelector('svg');
const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
let cur=0, playing=!reduce, speed=1, t0=performance.now(), pkEls=[];
const $=id=>document.getElementById(id);
function pathOf(id){return document.getElementById('e-'+id)}
function enter(i){
  cur=(i+STEPS.length)%STEPS.length; t0=performance.now();
  const s=STEPS[cur], on=new Set(s.nodes);
  document.querySelectorAll('.node').forEach(n=>{const id=n.id.slice(2);n.classList.toggle('on',on.has(id));n.classList.toggle('dim',!on.has(id))});
  const eds=new Set(s.packets.map(p=>p[0]));
  document.querySelectorAll('.edge.hot').forEach(e=>{const base=e.previousElementSibling.id.slice(2);e.classList.toggle('on',eds.has(base))});
  pkEls.forEach(p=>p.remove());
  pkEls=s.packets.map(()=>{const c=document.createElementNS('http://www.w3.org/2000/svg','circle');c.setAttribute('r',8);c.setAttribute('class','pk');c.style.display='none';svg.appendChild(c);return c});
  $('title').textContent=s.title; $('desc').textContent=s.desc; $('badge').textContent=s.badge;
  document.querySelectorAll('.dot').forEach((d,k)=>{d.classList.toggle('cur',k===cur);d.setAttribute('aria-current',k===cur?'step':'false')});
  location.hash='step='+(cur+1);
}
function frame(now){
  const el=(now-t0)*speed, s=STEPS[cur];
  s.packets.forEach((p,j)=>{
    const a=400+j*(PK_MS+150), f=(el-a)/PK_MS, c=pkEls[j]; if(!c) return;
    if(f<0||f>1){c.style.display='none';return}
    const path=pathOf(p[0]); if(!EDGE_LEN[p[0]]) EDGE_LEN[p[0]]=path.getTotalLength();
    const L=EDGE_LEN[p[0]], d=(p[1]?1-f:f)*L, pt=path.getPointAtLength(d);
    c.setAttribute('cx',pt.x);c.setAttribute('cy',pt.y);c.style.display='';
  });
  if(playing&&el>STEP_MS) enter(cur+1);
  requestAnimationFrame(frame);
}
function setPlaying(v){playing=v;$('play').textContent=v?'⏸ 일시정지':'▶ 재생';t0=performance.now()-(v?0:0)}
function build(){
  STEPS.forEach((_,i)=>{const b=document.createElement('button');b.className='dot';b.textContent=i+1;b.title=STEPS[i].title;b.setAttribute('aria-label','단계 '+(i+1)+': '+STEPS[i].title);b.onclick=()=>{enter(i)};$('dots').appendChild(b)});
  $('prev').onclick=()=>enter(cur-1); $('next').onclick=()=>enter(cur+1);
  $('play').onclick=()=>{setPlaying(!playing)};
  $('speed').onchange=e=>{speed=+e.target.value};
  addEventListener('keydown',e=>{if(e.key==='ArrowRight')enter(cur+1);else if(e.key==='ArrowLeft')enter(cur-1);else if(e.key===' '&&e.target.tagName!=='BUTTON'){e.preventDefault();setPlaying(!playing)}});
  const H=location.hash, m=H.match(/step=(\\d+)/), p=H.match(/t=(\\d+)/);
  enter(m?(+m[1]-1):0); setPlaying(playing);
  if(/pause/.test(H)){setPlaying(false); speed=0.0001; t0=performance.now()-(p?+p[1]:0)/speed}
  requestAnimationFrame(frame);
}
build();
</script>
</body>
</html>
"""


def build_html() -> str:
    steps_js = json.dumps([dict(title=s["title"], desc=s["desc"], badge=s["badge"], nodes=s["nodes"], packets=[list(p) for p in s["packets"]]) for s in STEPS], ensure_ascii=False)
    gl = "".join(f"<dt>{html.escape(a)}</dt><dd>{html.escape(b)}</dd>" for a, b in GLOSSARY)
    out = (HTML_TEMPLATE.replace("__COMMON__", STYLE_COMMON).replace("__SVGSTYLE__", STYLE_SVG).replace("__DEFS__", DEFS)
           .replace("__SCENE__", scene_svg(False)).replace("__STEPS__", steps_js).replace("__GLOSSARY__", gl)
           .replace("__STEPMS__", str(int(STEP_S * 1000))).replace("__PKMS__", str(int(PACKET_S * 1000))))
    return out


if __name__ == "__main__":
    (OUT / "PetMind_동작_애니메이션.html").write_text(build_html(), encoding="utf-8")
    (OUT / "PetMind_동작_애니메이션.svg").write_text(build_svg(), encoding="utf-8")
    print("wrote", OUT / "PetMind_동작_애니메이션.html", OUT / "PetMind_동작_애니메이션.svg")
