"""Local-only, fixed-source camera preview. Never persists frames."""
import os
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

router = APIRouter(prefix='/camera', tags=['camera'])
MAX_FRAME = 2 * 1024 * 1024


@router.get('/snapshot')
def snapshot():
    url = os.getenv('PETMIND_CAMERA_SNAPSHOT_URL', '')
    if not url:
        raise HTTPException(503, '라즈베리파이 카메라 연결이 설정되지 않았습니다.')
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
        raise HTTPException(503, '카메라 영상을 받지 못했습니다. Pi·웹캠·SSH 연결을 확인하세요.') from None
    return Response(bytes(data), media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


@router.get('/view', response_class=HTMLResponse)
def view():
    return HTMLResponse('''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PetMind 최근 카메라 장면</title>
<style>body{font:16px system-ui;background:#f8faf9;color:#244437;margin:16px}img{width:100%;max-height:65vh;object-fit:contain;background:#e8eeeb;border-radius:12px}button{padding:10px;margin-bottom:12px}#state{min-height:48px}</style>
<h3>라즈베리파이 · 최근 카메라 장면</h3>
<p>최근 화면을 주기적으로 확인합니다. 자동 외출 수집 중에는 약 5초 단위 장면이며 지연될 수 있습니다. 이 보기 버튼은 녹화·음성 분석을 시작하지 않습니다.</p>
<button id="toggle">카메라 보기 시작</button><div id="state" role="status">중지됨</div><img id="frame" hidden alt="라즈베리파이 웹캠 최근 화면">
<script>
let running=false, epoch=0, timer, objectUrl;
const button=document.getElementById('toggle'), state=document.getElementById('state'), frame=document.getElementById('frame');
function clearFrame(){frame.hidden=true;frame.removeAttribute('src');if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=null;}
async function refresh(e){
 if(!running||e!==epoch)return;
 try{const res=await fetch('/camera/snapshot',{cache:'no-store',signal:AbortSignal.timeout(6000)});
 if(!res.ok)throw Error('카메라 연결 불가 · Pi·웹캠·SSH 설정을 확인하고 다시 시작하세요.');
 const blob=await res.blob();if(!running||e!==epoch)return;
 clearFrame();objectUrl=URL.createObjectURL(blob);frame.src=objectUrl;frame.hidden=false;
 state.textContent='연결됨 · 수신 '+new Date().toLocaleTimeString();
 }catch(err){if(e!==epoch)return;clearFrame();state.textContent=err.message;}
 if(running&&e===epoch)timer=setTimeout(()=>refresh(e),500);
}
button.onclick=()=>{running=!running;epoch++;clearTimeout(timer);button.textContent=running?'보기 중지':'카메라 보기 시작';clearFrame();state.textContent=running?'연결 중…':'중지됨';if(running)refresh(epoch);};
document.addEventListener('visibilitychange',()=>{if(document.hidden&&running)button.click();});
</script></html>''', headers={'Cache-Control': 'no-store'})
