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
# 배치 원칙: 큰 줄기는 위 줄에서 왼쪽→오른쪽(마이크·웹캠 → 수집 → YAMNet → DB), DB에서 아래로 내려가
# 과거 기록 검색(MCP) → 오른쪽 밖의 클라우드 LLM, LLM의 제안은 아래 줄의 API로 돌아온다.
# 사용자 쪽(보호자 화면, 음악 명령, 스피커)은 아래 줄에서 오른쪽→왼쪽. 화살표는 대부분 직선이고 교차하지 않는다.
ZONES = [
    ("device", 24, 70, 212, 440, "PC에 연결된 장치"),
    ("server", 256, 70, 688, 440, "Windows PC (로컬 실행)"),
    ("cloud", 964, 210, 212, 190, "외부 클라우드 · 인터넷"),
]
# id: (x, y, w, h, 제목, 설명(\n으로 줄 나눔), 점선 여부)
NODES = {
    "dev": (40, 118, 176, 90, "마이크 · 웹캠", "노트북 내장 · 재생음 확인\n실제 강아지는 미확인", False),
    "spk": (40, 388, 176, 90, "스피커", "가상 실행\n물리 미연결", True),
    "agent": (272, 118, 184, 90, "수집 프로그램", "FFmpeg 5초 구간 · 업로드\n후보면 전후 영상 저장", False),
    "audio": (508, 118, 184, 90, "YAMNet (로컬)", "Bark 점수 계산\n기준 0.05 넘으면 후보", False),
    "db": (744, 118, 184, 90, "기록 DB (SQLite)", "상태 저장\n관찰 · 의견 · 제안", False),
    "rag": (744, 253, 184, 90, "과거 기록 검색", "MCP · 같은 반려견의\n과거 기록만", False),
    "api": (744, 388, 184, 90, "API · 제안 수신", "근거 ID 검사\n실패 시 규칙 제공자", False),
    "view": (508, 388, 184, 90, "보호자 화면", "확인 · 의견 · 승인\n폰·PC 브라우저 (Flutter)", False),
    "cmd": (272, 388, 184, 90, "음악 명령 관리", "요청 → 수신 → 완료", False),
    "llm": (974, 262, 192, 90, "클라우드 LLM", "Google Gemini API\n외부 서비스", False),
}
# id: (path, 양방향 여부)
EDGES = {
    "dev_agent": ("M216,163 H270", False),
    "agent_audio": ("M456,163 H506", False),
    "audio_db": ("M692,150 H742", False),
    "db_rag": ("M836,208 V251", False),
    "rag_llm": ("M928,298 H972", False),
    "llm_api": ("M1070,352 V433 H930", False),
    "api_db": ("M790,388 V360 H728 V194 H742", False),
    "api_view": ("M744,433 H694", False),
    "view_db": ("M600,388 V374 H708 V176 H742", True),
    "view_cmd": ("M508,433 H458", False),
    "cmd_spk": ("M272,433 H218", True),
}
# 화살표 라벨: 간선 id -> (x, y, 글자). 교수님 스케치의 'wav', '짖음 감지' 표기
EDGE_LABELS = {
    "agent_audio": (481, 152, "WAV"),
    "audio_db": (717, 142, "짖음\n감지"),
    "view_remote": (600, 498, "집 밖: Tailscale VPN 경유"),
}
# 단계: 제목, 설명, 배지, 강조 노드, [(간선, 역방향)] 순차 신호
STEPS = [
    dict(title="1. 외출을 시작합니다",
         desc="보호자가 화면에서 외출을 시작하면 서버에 수집 요청이 만들어집니다. PC의 수집 프로그램이 이 요청을 확인해 마이크·웹캠 수집을 시작합니다.",
         badge="구현됨 · 노트북 마이크·웹캠으로 10분 수집, 끊겨도 자동 재시작 확인", nodes=["view", "db", "agent"], packets=[("view_db", False)]),
    dict(title="2. 소리와 영상을 모읍니다",
         desc="PC에 직접 연결한 마이크와 웹캠의 입력을 약 5초 단위 구간으로 나눠 임시 보관합니다. 오래된 구간은 지워 저장 공간을 아낍니다.",
         badge="구현됨 · 640×480 30fps 미리보기, 스피커로 튼 소리를 내장 마이크로 감지 / 실제 강아지는 미확인", nodes=["dev", "agent"],
         packets=[("dev_agent", False)]),
    dict(title="3. YAMNet이 짖음을 감지합니다",
         desc="수집 프로그램이 5초 WAV를 서버 API에 올리면, 서버가 PC에서 로컬로 실행 중인 YAMNet 서비스를 불러 개 짖음(Bark) 점수를 읽습니다. 점수가 기준(0.05)을 넘으면 짖음 후보입니다. 감정이나 질환은 판단하지 않습니다.",
         badge="구현됨 · 공개 음원 평가: 짖음 ESC-50 40/40·FSD50K 40/49 감지, 비개 소리 오탐 1~2% / 짧고 약한 짖음은 놓침", nodes=["agent", "audio"],
         packets=[("agent_audio", False)]),
    dict(title="4. 짖음 후보면 앞뒤 장면과 함께 DB에 저장합니다",
         desc="점수가 기준을 넘으면 수집 프로그램이 그 앞뒤 각 5초 영상을 잘라 서버에 올리고, 서버가 관찰에 연결해 저장합니다. 관찰 ID, 시각, 출처, 분석 결과는 반려견별로 SQLite에 저장되며 서버를 다시 시작해도 남습니다. 카메라는 보호자가 직접 확인하는 용도이고 영상으로 행동을 자동 판단하지 않습니다.",
         badge="구현됨 · 실제 마이크로 감지한 구간의 35초 사건 영상(영상+소리) 저장 확인", nodes=["audio", "db"],
         packets=[("audio_db", False)]),
    dict(title="5. 보호자가 직접 확인합니다",
         desc="폰이나 PC 브라우저의 화면에서 원본 소리와 영상을 재생하고 '개 짖음 소리 / TV 소리 / 잘 모르겠음' 같은 의견을 남깁니다. 집 와이파이에서는 주소와 접속 키로, 집 밖에서는 Tailscale VPN을 거쳐 같은 주소로 접속하며 공개 인터넷에는 열지 않습니다. AI 판정과 보호자 의견은 따로 보관됩니다.",
         badge="구현됨 · 폰(집 와이파이·모바일 데이터)과 다른 PC 접속 확인. 느린 모바일 망에서는 카메라 화면이 끊김", nodes=["view", "db"], packets=[("view_db", True), ("view_db", False)]),
    dict(title="6. 과거 기록을 찾아 클라우드 LLM에 보냅니다",
         desc="같은 반려견의 과거 기록만 MCP로 조회해, 기록에서 뽑은 문장을 외부 클라우드 LLM(Gemini)에 전달합니다. 음원과 영상은 보내지 않습니다. API 키가 없으면 외부로 보내지 않고 PC의 규칙 제공자가 대신합니다.",
         badge="구현됨 · Gemini 실호출 확인(귀가 설명 3/3, 합성·공개 음원 시연 자료)", nodes=["db", "rag", "llm"],
         packets=[("db_rag", False), ("rag_llm", False)]),
    dict(title="7. LLM이 근거를 바탕으로 만든 확인 제안을 받습니다",
         desc="클라우드 LLM이 기록을 근거로 보호자가 확인할 제안을 만들어 API로 돌려줍니다. 진단이나 감정 판정이 아닙니다. 서버가 인용한 근거 ID를 검사해 보호자 화면에 표시하고(케어 제안은 이력으로 DB에 저장, 귀가 요약 설명은 요청할 때마다 만들어 보여 줌), 호출 실패나 잘못된 인용이면 규칙 제공자로 대체합니다.",
         badge="구현됨 · 인용 범위만 검사, 문장별 수치·인과 검증은 남아 있음", nodes=["llm", "api", "db", "view"],
         packets=[("llm_api", False), ("api_db", False), ("api_view", False)]),
    dict(title="8. 승인하면 음악 명령을 보냅니다",
         desc="음성 후보와 보호자의 '개 소리' 확인 의견이 함께 있을 때만 음악이 제안됩니다. 보호자가 승인하면 명령이 요청 → 수신 → 완료 순으로 진행하고, 응답이 없으면 시간 초과로 기록합니다.",
         badge="가상 실행 · 실제 스피커는 연결하지 않음", nodes=["view", "cmd", "spk"],
         packets=[("view_cmd", False), ("cmd_spk", False), ("cmd_spk", True)]),
]
STEP_NODES = [set(s["nodes"]) for s in STEPS]
GLOSSARY = [
    ("짖음 후보", "모델이 '개 짖음 소리일 수 있다'고 본 5초 구간입니다. 실제 짖음 횟수나 감정을 뜻하지 않습니다."),
    ("YAMNet", "구글이 미리 학습해 둔 소리 분류 모델입니다. 이 시스템에서는 PC에서 로컬로 실행해 5초 소리에서 'Bark(개 짖음)' 점수를 읽어 짖음 후보를 찾습니다. 점수는 확률이나 정확도가 아닙니다."),
    ("RAG · MCP", "질문과 관련된 과거 기록을 먼저 찾아 AI에게 근거로 건네는 방식입니다. MCP는 그 검색 도구를 부르는 표준 방법입니다."),
    ("클라우드 LLM (Gemini)", "인터넷의 외부 서비스로 동작하는 생성형 AI입니다. API 키가 없거나 호출이 실패하면 PC의 규칙 기반 제공자가 대신 설명합니다."),
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
            + "".join(f'<text class="ns" x="{x + 16}" y="{y + 52 + 18 * i}">{html.escape(t)}</text>' for i, t in enumerate(sub.split("\n")))
            + f'<rect class="hl" x="{x - 3}" y="{y - 3}" width="{w + 6}" height="{h + 6}" rx="14"{hl_attrs}/></g>')


def scene_svg(animated_svg: bool) -> str:
    total = STEP_S * len(STEPS)
    out = []
    for zid, x, y, w, h, label in ZONES:
        zc = "zone cloud" if zid == "cloud" else "zone"
        out.append(f'<rect class="{zc}" x="{x}" y="{y}" width="{w}" height="{h}" rx="18"/>'
                   f'<text class="zt" x="{x + 18}" y="{y + 28}">{html.escape(label)}</text>')
    for eid, (d, both) in EDGES.items():
        mk = ' marker-start="url(#ah)" marker-end="url(#ah)"' if both else ' marker-end="url(#ah)"'
        hl = ""
        if animated_svg:
            iv = [(i * STEP_S, (i + 1) * STEP_S) for i, s in enumerate(STEPS) if any(p[0] == eid for p in s["packets"])]
            v, k = lerp_intervals(iv, total)
            hl = f'<animate attributeName="opacity" values="{v}" keyTimes="{k}" dur="{total}s" repeatCount="indefinite"/>'
        out.append(f'<path class="edge" id="e-{eid}" d="{d}"{mk}/><path class="edge hot" d="{d}" opacity="0"{mk}>{hl}</path>')
    for _eid, (lx, ly, ltxt) in EDGE_LABELS.items():
        rows = ltxt.split("\n")  # 마지막 줄이 ly, 앞 줄은 위로 쌓는다
        for i, row in enumerate(rows):
            out.append(f'<text class="el" x="{lx}" y="{ly - 12 * (len(rows) - 1 - i)}" text-anchor="middle">{html.escape(row)}</text>')
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
:root{--bg:#f6f7fb;--zone:#eceef6;--zl:#cfd3e6;--node:#fff;--line:#8d93ad;--tx:#1d2033;--mu:#5b607a;--ac:#5b4bd6;--ok:#16a34a;--hot:#5b4bd6;--cap:#ffffff;--cloudfill:#e8edff}
@media (prefers-color-scheme:dark){:root{--bg:#12141c;--zone:#1b1e2b;--zl:#2c3044;--node:#232738;--line:#6b7190;--tx:#eceef8;--mu:#a2a8c4;--ac:#9b8cff;--ok:#4ade80;--hot:#9b8cff;--cap:#1b1e2b;--cloudfill:#1c2342}}
"""
STYLE_SVG = """
.zone{fill:var(--zone);stroke:var(--zl)}.zone.cloud{fill:var(--cloudfill);stroke:var(--ac);stroke-dasharray:7 5}.zt{fill:var(--mu);font:700 15px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
.box{fill:var(--node);stroke:var(--line);stroke-width:1.6}.nt{fill:var(--tx);font:700 18px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
.ns{fill:var(--mu);font:13.5px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}.hl{fill:none;stroke:var(--hot);stroke-width:3.5;opacity:0}
.edge{fill:none;stroke:var(--line);stroke-width:2.2}.edge.hot{stroke:var(--hot);stroke-width:3.4}.pk{fill:var(--ok);stroke:var(--bg);stroke-width:2}
.el{fill:var(--mu);font:600 11px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}.ah{fill:var(--line)}.cap{fill:var(--tx);font:700 21px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}.cd{fill:var(--tx);font:16px 'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif}
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
<p class="note">범례: 실선 상자는 구현·검증한 부분, 점선 상자는 가상 실행이거나 실장비 미검증인 부분입니다. 그림은 흐름을 단순화했습니다. 수집 프로그램·보호자 화면·가상 장치는 모두 서버 API(FastAPI)를 거쳐 DB와 YAMNet 서비스를 씁니다. 초록 점은 데이터·명령이 이동하는 모습입니다. 키보드 ← → 로 단계를 넘기고 Space로 재생/정지합니다.</p>
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
