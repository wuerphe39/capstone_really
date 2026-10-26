"""Fixed-source camera view (live MJPEG stream and single snapshot). Never persists frames.

On this PC the page pushes the full 30 fps stream. For a remote viewer (phone, VPN) that would need ~5 Mbit/s and any
dip in the mobile network makes the backlog grow into seconds of delay, so remote viewers get small, low-quality
snapshots that the page pulls one at a time: it never has more than one frame in flight, so the delay cannot build up
and the picture rate simply follows the connection speed.
"""
import os
import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from .. import access

router = APIRouter(prefix='/camera', tags=['camera'])
MAX_FRAME = 2 * 1024 * 1024


def shrink(data: bytes, width: int, quality: int) -> bytes:
    """Scale a JPEG down to `width` pixels (never up) and re-encode it. The original is returned if OpenCV is missing."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return data
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[1] <= width:
        return data
    height = max(1, round(image.shape[0] * width / image.shape[1]))
    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    ok, out = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return out.tobytes() if ok else data


@router.get('/snapshot')
def snapshot(width: int | None = Query(default=None, ge=96, le=1280), quality: int = Query(default=60, ge=20, le=95)):
    url = os.getenv('PETMIND_CAMERA_SNAPSHOT_URL', '')
    if not url:
        raise HTTPException(503, 'PC 카메라 미리보기 연결이 설정되지 않았습니다.')
    try:
        with requests.get(url, timeout=(2, 3), stream=True, allow_redirects=False) as upstream:
            if upstream.status_code != 200:
                raise ValueError('camera unavailable')
            data = bytearray()
            for chunk in upstream.iter_content(65536):
                data.extend(chunk)
                if len(data) > MAX_FRAME:
                    raise ValueError('frame too large')
            if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
                raise ValueError('invalid jpeg')
    except (requests.RequestException, ValueError):
        raise HTTPException(503, '카메라 영상을 받지 못했습니다. 웹캠과 수집 프로그램 연결을 확인하세요.') from None
    body = shrink(bytes(data), width, quality) if width else bytes(data)
    return Response(body, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


@router.get('/stream')
def stream():
    """Relay the capture program's MJPEG stream (the same host/port as PETMIND_CAMERA_SNAPSHOT_URL)."""
    base = os.getenv('PETMIND_CAMERA_SNAPSHOT_URL', '')
    if not base:
        raise HTTPException(503, 'PC 카메라 미리보기 연결이 설정되지 않았습니다.')
    try:
        upstream = requests.get(base.rsplit('/', 1)[0] + '/stream', stream=True, timeout=(2, 5), allow_redirects=False)
    except requests.RequestException:
        raise HTTPException(503, '카메라 영상을 받지 못했습니다. 웹캠과 수집 프로그램 연결을 확인하세요.') from None
    content_type = upstream.headers.get('content-type', '')
    if upstream.status_code != 200 or not content_type.startswith('multipart/x-mixed-replace'):
        upstream.close()
        raise HTTPException(503, '카메라 영상을 받지 못했습니다. 웹캠과 수집 프로그램 연결을 확인하세요.')

    def body():
        try:
            for chunk in upstream.iter_content(16384):
                if chunk:
                    yield chunk
        except requests.RequestException:
            return
        finally:
            upstream.close()
    return StreamingResponse(body(), media_type=content_type, headers={'Cache-Control': 'no-store'})


@router.get('/view', response_class=HTMLResponse)
def view(request: Request, mode: str | None = Query(default=None, pattern='^(push|poll)$')):
    """`push`: continuous stream, only for this PC. `poll`: small frames pulled one by one; remote viewers always get this
    (the continuous stream is what builds up seconds of delay on a mobile connection), whatever `mode` they ask for."""
    host = request.client.host if request.client else ''
    is_remote = access.client_kind(host) != 'loopback'
    chosen = 'poll' if is_remote else (mode or 'push')
    # Only this PC may switch views (handy for comparing); a remote viewer has nothing to switch to.
    switch_link = '' if is_remote else (
        '<p><a href="/camera/view?mode=' + ('poll' if chosen == 'push' else 'push') + '">'
        + ('저대역 보기로 바꾸기' if chosen == 'push' else '30fps 연속 보기로 바꾸기') + '</a></p>\n')
    note = ('웹캠이 내는 속도에 따라 초당 최대 30장' if chosen == 'push' else
            '느린 망에서도 지연이 쌓이지 않도록 작은 화면을 한 장씩 받아 옵니다(망 속도에 맞춰 화질·장수를 자동 조절)')
    if chosen == 'push':
        script = """
function start(){running=true;button.textContent='보기 중지';state.textContent='연결 중…';frame.hidden=false;frame.src='/camera/stream?'+Date.now();}
frame.onload=()=>{if(running)state.textContent='연결됨 · 실시간 '+new Date().toLocaleTimeString();};
frame.onerror=()=>{if(running)stop('카메라 연결 불가 · 웹캠·수집 프로그램 설정을 확인하고 다시 시작하세요.');};
"""
    else:
        script = """
// Remote view: small frames pulled over HTTP, up to DEPTH requests in flight. Every request fetches the newest frame at
// that moment, a frame that arrives after a newer one is dropped, so a slow connection lowers the picture rate (and
// picture size) instead of building up delay.
const TIERS=[{w:240,q:45},{w:360,q:55},{w:480,q:60}];                   // frame width and JPEG quality, adapted to the connection
const GAP=60;                                                           // at most about 16 requests per second
let tier=1,depth=2,fast=0,failures=0,inflight=0,lastStart=0,lastShown=0,shown=null,rtt=0;
const shownAt=[];                                                       // times of the last shown frames, for the on-screen rate
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function fetchOne(began,gen){
  inflight++;
  try{
    const t=TIERS[tier];
    const r=await fetch('/camera/snapshot?width='+t.w+'&quality='+t.q+'&t='+Date.now(),{cache:'no-store'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    const blob=await r.blob();
    if(!running||gen!==generation)return;
    failures=0; const spent=performance.now()-began;
    if(began>lastShown){                                                 // never show an older frame after a newer one
      lastShown=began; const url=URL.createObjectURL(blob); frame.src=url; if(shown)URL.revokeObjectURL(shown); shown=url;
      const nowMs=performance.now(); shownAt.push(nowMs); while(shownAt.length&&nowMs-shownAt[0]>2000)shownAt.shift();
      state.textContent='연결됨 · 저대역 보기 '+t.w+'px · '+Math.round(blob.size/1024)+' KB/장 · 초당 '+(shownAt.length/2).toFixed(0)+'장 · 응답 '+Math.round(rtt||spent)+' ms';
    }
    rtt=rtt?rtt*0.8+spent*0.2:spent;                                     // smoothed response time
    if(spent>900){if(tier>0)tier--;depth=1;fast=0;}                      // congested: smaller pictures, one request at a time
    else{
      depth=Math.max(1,Math.min(4,Math.ceil(rtt/GAP)+1));                // slower answers need more requests in flight to keep the rate
      if(spent<350){if(++fast>=8){fast=0;if(tier<TIERS.length-1)tier++;}} else fast=0;
    }
  }catch(e){
    if(gen===generation&&++failures>=5){stop('카메라 연결 불가 · 웹캠·수집 프로그램 설정을 확인하고 다시 시작하세요.');}
  }finally{inflight--;}
}
let generation=0;
async function loop(gen){
  while(running&&gen===generation){
    const now=performance.now();
    if(inflight<depth&&now-lastStart>=GAP){lastStart=now;fetchOne(now,gen);}
    await sleep(failures?600:8);
  }
}
function start(){running=true;generation++;inflight=0;lastShown=0;failures=0;rtt=0;depth=2;shownAt.length=0;button.textContent='보기 중지';state.textContent='연결 중…';frame.hidden=false;loop(generation);}
"""
    html = ('<!doctype html><html lang="ko"><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            '<title>PetMind 실시간 카메라 장면</title>\n'
            '<style>body{font:16px system-ui;background:#f8faf9;color:#244437;margin:16px}img{width:100%;max-height:65vh;object-fit:contain;background:#e8eeeb;border-radius:12px}button{padding:10px;margin-bottom:12px}a{color:#4b5ec9}</style>\n'
            '<h3>PC 웹캠 · 실시간 카메라 장면</h3>\n'
            f'<p>수집 중인 웹캠 화면을 바로 보여 줍니다({note}). 이 보기 버튼은 녹화·음성 분석을 시작하지 않으며 화면은 저장되지 않습니다.</p>\n'
            '<button id="toggle">카메라 보기 시작</button><div id="state" role="status">중지됨</div><img id="frame" hidden alt="PC 웹캠 실시간 화면">\n'
            + switch_link +
            '<script>\nlet running=false;\n'
            "const button=document.getElementById('toggle'), state=document.getElementById('state'), frame=document.getElementById('frame');\n"
            "function stop(message){running=false;frame.hidden=true;frame.removeAttribute('src');button.textContent='카메라 보기 시작';state.textContent=message||'중지됨';}\n"
            + script +
            "button.onclick=()=>{running?stop():start();};\n"
            "document.addEventListener('visibilitychange',()=>{if(document.hidden&&running)stop();});\n"
            '</script></html>')
    return HTMLResponse(html, headers={'Cache-Control': 'no-store'})
