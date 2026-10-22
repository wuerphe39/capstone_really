"""Local-only, fixed-source camera view (live MJPEG stream and single snapshot). Never persists frames."""
import os
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response, StreamingResponse

router = APIRouter(prefix='/camera', tags=['camera'])
MAX_FRAME = 2 * 1024 * 1024


@router.get('/snapshot')
def snapshot():
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
    return Response(bytes(data), media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


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
def view():
    return HTMLResponse('''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PetMind 실시간 카메라 장면</title>
<style>body{font:16px system-ui;background:#f8faf9;color:#244437;margin:16px}img{width:100%;max-height:65vh;object-fit:contain;background:#e8eeeb;border-radius:12px}button{padding:10px;margin-bottom:12px}</style>
<h3>PC 웹캠 · 실시간 카메라 장면</h3>
<p>수집 중인 웹캠 화면을 바로 보여 줍니다(웹캠이 내는 속도에 따라 초당 최대 30장). 이 보기 버튼은 녹화·음성 분석을 시작하지 않으며 화면은 저장되지 않습니다.</p>
<button id="toggle">카메라 보기 시작</button><div id="state" role="status">중지됨</div><img id="frame" hidden alt="PC 웹캠 실시간 화면">
<script>
let running=false;
const button=document.getElementById('toggle'), state=document.getElementById('state'), frame=document.getElementById('frame');
function stop(message){running=false;frame.hidden=true;frame.removeAttribute('src');button.textContent='카메라 보기 시작';state.textContent=message||'중지됨';}
function start(){running=true;button.textContent='보기 중지';state.textContent='연결 중…';frame.hidden=false;frame.src='/camera/stream?'+Date.now();}
frame.onload=()=>{if(running)state.textContent='연결됨 · 실시간 '+new Date().toLocaleTimeString();};
frame.onerror=()=>{if(running)stop('카메라 연결 불가 · 웹캠·수집 프로그램 설정을 확인하고 다시 시작하세요.');};
button.onclick=()=>{running?stop():start();};
document.addEventListener('visibilitychange',()=>{if(document.hidden&&running)stop();});
</script></html>''', headers={'Cache-Control': 'no-store'})
