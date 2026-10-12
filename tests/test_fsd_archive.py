import io
import time
import zipfile

import pytest

from scripts.prepare_fsd50k_subset import SplitZip


def test_zip_directory_and_crc_without_network(monkeypatch):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('audio/test.wav',b'wave fixture'*100)
    content = stream.getvalue()
    monkeypatch.setattr(SplitZip,'read',lambda self,start,count:content[start:start+count])
    archive = SplitZip([{'size':len(content)}], time.monotonic() + 60)
    assert archive.extract('audio/test.wav') == b'wave fixture'*100
    archive.entries['audio/test.wav']['crc'] = 0
    with pytest.raises(ValueError,match='CRC'):
        archive.extract('audio/test.wav')
