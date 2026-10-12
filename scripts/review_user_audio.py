"""Operator CLI. Listen and verify first; no inference is promoted to ground truth.

TV playback of barking is 'dog' for acoustic classification, even when the
guardian labels its source external_or_tv. Never infer this mapping automatically.
"""
import argparse
import json
from pathlib import Path

from petmind.backend.database import SessionLocal, init_db
from petmind.backend.services.audio_training import build_manifest, resolve_manifest, verify


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command',required=True)
    check = commands.add_parser('verify')
    check.add_argument('clip_id'); check.add_argument('--label',choices=['dog','other'],required=True)
    check.add_argument('--reviewer',required=True); check.add_argument('--reason',required=True)
    export = commands.add_parser('export')
    export.add_argument('--output',type=Path,default=Path('artifacts/user_audio_training/manifest.json'))
    validate = commands.add_parser('validate')
    validate.add_argument('manifest',type=Path)
    args = parser.parse_args(); init_db()
    with SessionLocal() as db:
        if args.command == 'verify':
            verify(db,args.clip_id,args.label,args.reviewer,args.reason)
            print('independent review recorded; model unchanged')
        elif args.command == 'export':
            manifest = build_manifest(db)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'eligible':len(manifest['records']),'excluded':len(manifest['excluded'])}))
        else:
            records = resolve_manifest(db,json.loads(args.manifest.read_text(encoding='utf-8')))
            print(json.dumps({'validated':len(records)}))


if __name__ == '__main__':
    main()
