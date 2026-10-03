import json
import zipfile
import pytest
from scripts.build_release import build_release, ROOT_FILES


def test_release_is_deterministic_and_contains_only_delivery_files(tmp_path):
    root=tmp_path/'project'
    root.mkdir()
    for name in ROOT_FILES: (root/name).write_text('safe example',encoding='utf-8')
    for name in ['data/secret.json','.env','frontend/.env','frontend/private.zip','researchpilot/__pycache__/cached.py','artifacts/result.json']:
        file=root/name
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text('PRIVATE DATA')
    (root/'researchpilot'/'app.py').write_text('# app')
    (root/'frontend'/'mark.svg').write_text('<svg/>')
    first=build_release(root,tmp_path/'first.zip')
    second=build_release(root,tmp_path/'second.zip')
    assert first['sha256']==second['sha256']
    with zipfile.ZipFile(first['path']) as bundle:
        assert 'researchpilot/app.py' in bundle.namelist()
        assert 'frontend/mark.svg' in bundle.namelist()
        assert b'PRIVATE DATA' not in b''.join(bundle.read(n) for n in bundle.namelist())
        manifest=json.loads(bundle.read('release-manifest.json'))
        assert set(manifest['files']) == set(bundle.namelist())-{'release-manifest.json'}
    with pytest.raises(FileExistsError): build_release(root,tmp_path/'first.zip')
