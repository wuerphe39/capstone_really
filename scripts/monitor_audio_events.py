"""Capture synchronized A/V segments, upload audio, retain LSTM-triggered video.

File replay is paced and explicitly labelled. Live inputs are provided as an
FFmpeg argument JSON array (no shell). Requires ffmpeg with libx264 and AAC.
"""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

import requests
import soundfile as sf

from pet_monitor.event_video import EventPlanner, candidate_windows


def run_ffmpeg(executable, arguments):
    subprocess.run([executable,'-hide_banner','-loglevel','error','-nostdin','-y',*arguments],
                   check=True, timeout=120, stdout=subprocess.DEVNULL)


def build_capture_command(ffmpeg, input_args, video_map, audio_map, folder):
    return [ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-y',*input_args,
            '-map',video_map,'-map',audio_map,'-vf','scale=640:-2','-r','10',
            '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
            '-g','50','-keyint_min','50','-sc_threshold','0',
            '-force_key_frames','expr:gte(t,n_forced*5)',
            '-c:a','aac','-ar','16000','-ac','1',
            '-f','segment','-segment_time','5','-segment_time_delta','0.1','-reset_timestamps','1',
            '-segment_list',str(folder/'segments.csv'),'-segment_list_type','csv',
            str(folder/'seg-%06d.mp4')]


def export_event(ffmpeg, segments, event, directory):
    selected=[s for s in segments if s['end']>event.start and s['start']<event.end]
    if not selected or any(b['start']-a['end']>.15 for a,b in zip(selected,selected[1:])):
        raise ValueError('buffer_gap')
    start=max(event.start,selected[0]['start']); end=min(event.end,selected[-1]['end'])
    if end<=start:
        raise ValueError('buffer_gap')
    manifest=directory/'concat.txt'
    # Segment names are generated locally; no untrusted path interpolation.
    manifest.write_text(''.join(f"file '{s['path'].name}'\n" for s in selected),encoding='utf-8')
    output=directory/'event.mp4'
    run_ffmpeg(ffmpeg,['-f','concat','-safe','1','-i',str(manifest),
        '-ss',f'{max(0.,start-selected[0]["start"]):.6f}','-t',f'{end-start:.6f}',
        '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
        '-c:a','aac','-movflags','+faststart',str(output)])
    return output,start


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--input',type=Path,help='A/V file replay, paced at original speed')
    source.add_argument('--input-args-file',type=Path,help='JSON array of FFmpeg live input arguments')
    parser.add_argument('--ffmpeg',default=shutil.which('ffmpeg'))
    parser.add_argument('--video-map',default='0:v:0')
    parser.add_argument('--audio-map',default='0:a:0')
    parser.add_argument('--base',default='http://127.0.0.1:8010')
    parser.add_argument('--pet-id',required=True)
    parser.add_argument('--outing-id')
    parser.add_argument('--new-outing',action='store_true')
    parser.add_argument('--store-consent',action='store_true')
    parser.add_argument('--demo-source',help='Attribution for public file replay; not a personal pet record')
    parser.add_argument('--pre-s',type=float,default=5)
    parser.add_argument('--post-s',type=float,default=5)
    parser.add_argument('--max-event-s',type=float,default=60)
    parser.add_argument('--retention-days',type=int,default=7,choices=range(1,31))
    parser.add_argument('--max-buffer-mb',type=int,default=128)
    parser.add_argument('--stop-file',type=Path)
    parser.add_argument('--progress-file',type=Path)
    parser.add_argument('--preview-file',type=Path)
    args=parser.parse_args()
    if not args.ffmpeg or not args.store_consent:
        parser.error('FFmpeg and --store-consent are required')
    if args.new_outing and args.outing_id:
        parser.error('choose --new-outing or --outing-id')
    if args.max_buffer_mb<16:
        parser.error('--max-buffer-mb must be at least 16')
    planner=EventPlanner(args.pre_s,args.post_s,args.max_event_s)
    kind='file_replay' if args.input else 'device'
    if args.demo_source and kind=='device':
        parser.error('public demo provenance is only valid for file replay')
    input_args=['-re','-i',str(args.input.resolve())] if args.input else json.loads(args.input_args_file.read_text(encoding='utf-8'))
    if not isinstance(input_args,list) or not all(isinstance(v,str) for v in input_args):
        parser.error('input arguments must be a JSON array of strings')
    base=args.base.rstrip('/'); session_id=uuid.uuid4().hex
    http=requests.Session()
    def post(route, **kw):
        response=http.post(base+route,timeout=60,**kw)
        if not response.ok:
            raise requests.HTTPError(f'{route}: {response.status_code} {response.text[:600]}',response=response)
        return response.json()
    outing=args.outing_id
    if args.new_outing:
        outing=post('/outings',json={'pet_id':args.pet_id,'input_mode':'live' if kind=='device' else 'uploaded_audio',
                                    'title':'장치 음성·사건 영상' if kind=='device' else '원본 파일 음성·사건 영상 재생'})['id']
    origin=datetime.now(timezone.utc)
    def iso(offset): return (origin+timedelta(seconds=offset)).isoformat()
    def log(**values): print(json.dumps(values,ensure_ascii=False),flush=True)
    with tempfile.TemporaryDirectory(prefix='petmind-capture-') as temporary:
        folder=Path(temporary); segments=[]; processed=set(); analysed_until=0.
        error_log=(folder/'capture.log').open('w',encoding='utf-8')
        command=build_capture_command(args.ffmpeg,input_args,args.video_map,args.audio_map,folder)
        command.remove('-nostdin')
        process=subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,stderr=error_log)
        stopping=False
        def publish(event):
            try:
                output,actual_start=export_event(args.ffmpeg,segments,event,folder)
            except (ValueError,subprocess.SubprocessError) as exc:
                reason='buffer_gap' if isinstance(exc,ValueError) else 'encode_failed'
                post('/event-videos/missing',json={'pet_id':args.pet_id,'clip_ids':event.clip_ids,'reason':reason})
                log(event_video='missing',reason=reason); return
            try:
                with output.open('rb') as stream:
                    result=post('/event-videos',params={'pet_id':args.pet_id,'clip_ids':event.clip_ids,
                        'started_at':iso(actual_start),'pre_s':args.pre_s,'post_s':args.post_s,
                        'store_consent':'true'},data=stream,headers={'Content-Type':'video/mp4'})
                log(event_video=result)
            except requests.RequestException:
                # A response may have been lost after commit; never overwrite an existing video.
                try: post('/event-videos/missing',json={'pet_id':args.pet_id,'clip_ids':event.clip_ids,'reason':'upload_failed'})
                except requests.RequestException: pass
                raise
            finally:
                output.unlink(missing_ok=True)
        try:
            while True:
                if args.stop_file and args.stop_file.exists() and not stopping:
                    stopping=True
                    if process.poll() is None:
                        process.stdin.write(b'q\n'); process.stdin.flush()
                if sum(p.stat().st_size for p in folder.glob('*.mp4'))>args.max_buffer_mb*1024*1024:
                    raise RuntimeError('capture buffer full; recording stopped to bound disk usage')
                listing=folder/'segments.csv'
                completed=list(csv.reader(listing.read_text(encoding='utf-8').splitlines())) if listing.exists() else []
                for row in completed:
                    if len(row)!=3 or row[0] in processed: continue
                    path=folder/Path(row[0]).name
                    start,end=float(row[1]),float(row[2])
                    if not path.is_file() or end<=start: continue
                    segment={'path':path,'start':start,'end':end}
                    segments.append(segment)
                    if args.preview_file:
                        args.preview_file.parent.mkdir(parents=True,exist_ok=True)
                        preview=args.preview_file.with_suffix('.tmp.jpg')
                        run_ffmpeg(args.ffmpeg,['-sseof','-0.2','-i',str(path),'-frames:v','1','-update','1',str(preview)])
                        preview.replace(args.preview_file)
                    wav=folder/'audio.wav'
                    run_ffmpeg(args.ffmpeg,['-i',str(path),'-vn','-ar','16000','-ac','1','-t',str(end-start),str(wav)])
                    # Demuxers may emit a completed segment ahead of wall clock;
                    # AAC padding can also extend its audio by a few samples.
                    # Wait for its actual sample end rather than submit future data.
                    due=(origin+timedelta(seconds=start+sf.info(wav).duration)).timestamp()
                    while time.time()<due:
                        time.sleep(max(0.,min(.2,due-time.time())))
                    params={'pet_id':args.pet_id,'store_consent':'true','retention_days':args.retention_days,
                            'captured_at':iso(start),'capture_kind':kind,'capture_session':session_id}
                    if outing: params['outing_id']=outing
                    if args.demo_source: params['demo_source']=args.demo_source
                    with wav.open('rb') as stream:
                        result=post('/audio-clips/upload',params=params,data=stream,headers={'Content-Type':'audio/wav'})
                    wav.unlink(missing_ok=True)
                    windows=candidate_windows(result['analysis'])
                    if args.progress_file:
                        progress=args.progress_file.with_suffix('.tmp')
                        progress.write_text(json.dumps({'at':time.time(),
                            'model_ready':bool(result['analysis'].get('audio_lstm'))}),encoding='utf-8')
                        progress.replace(args.progress_file)
                    for w in windows: planner.add(start+w['start_s'],start+w['end_s'],result['id'])
                    log(observation_id=result['observation_id'],dog_windows=len(windows),model_status=result['analysis'].get('model_status','ready'))
                    processed.add(row[0]); analysed_until=end
                    for event in planner.drain(analysed_until): publish(event)
                    oldest=min([analysed_until-args.pre_s-5]+[e.start for e in planner.pending])
                    for segment in list(segments):
                        if segment['end']<oldest:
                            segment['path'].unlink(missing_ok=True);segments.remove(segment)
                if process.poll() is not None:
                    # The encoder can close its final segment after the CSV snapshot
                    # above. Read it on the next iteration before draining events.
                    final_rows=list(csv.reader(listing.read_text(encoding='utf-8').splitlines())) if listing.exists() else []
                    if any(len(r)==3 and r[0] not in processed for r in final_rows):
                        continue
                    for event in planner.drain(analysed_until,final=True): publish(event)
                    if process.returncode:
                        raise RuntimeError('FFmpeg capture failed; verify input devices and maps')
                    break
                time.sleep(.2)
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill();process.wait()
            error_log.close()
            # On interruption, retain analysed audio and mark unpublished video explicitly.
            for event in planner.pending:
                try: post('/event-videos/missing',json={'pet_id':args.pet_id,'clip_ids':event.clip_ids,'reason':'camera_unavailable'})
                except requests.RequestException: pass
            if args.new_outing:
                post(f'/outings/{outing}/end',params={'pet_id':args.pet_id})
            http.close()


if __name__=='__main__':
    main()
