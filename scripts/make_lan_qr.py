"""Write a QR code (PNG) for the phone address that start_demo -Lan prints, so the access key need not be typed.

    python -m scripts.make_lan_qr "http://192.168.0.5:8010/?key=..." artifacts/demo/lan-qr.png

Needs the small pure-Python `segno` package (requirements-runtime.txt). Exit code 2 when it is missing, in which case the
launcher just prints the address.
"""
import sys
from pathlib import Path


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 1
    url, out = argv[0], Path(argv[1])
    try:
        import segno
    except ImportError:
        print('segno is not installed: pip install -r requirements-runtime.txt')
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    segno.make(url, error='m').save(str(out), scale=10, border=3)
    print(f'QR code written: {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
