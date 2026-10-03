"""Build a source release from an explicit allowlist; never include local data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from researchpilot import __version__

ROOT_FILES = {"README.md", "requirements.txt", "requirements-lock.txt", "requirements-dev.txt", "pytest.ini",
              "start.bat", "start.ps1", "Dockerfile", "compose.yaml", ".env.example", ".gitignore", ".dockerignore"}
TREES = {"researchpilot": {".py"}, "frontend": {".js", ".html", ".css", ".svg"}, "examples": {".json", ".log"},
         "deploy": {".example", ".service"},
         "evals": {".json"}, "docs": {".md", ".json"}, "tests": {".py"}, "scripts": {".py"}, ".github/workflows": {".yml"}}


def build_release(root, output):
    root, output = Path(root).resolve(), Path(output).absolute()
    candidates = [root / name for name in sorted(ROOT_FILES)]
    for tree, suffixes in TREES.items():
        base = root / tree
        if base.exists():
            candidates.extend(path for path in base.rglob('*') if path.is_file() and path.suffix in suffixes
                              and not any(part.startswith('.') or part == '__pycache__' for part in path.relative_to(base).parts))
    missing = [p.name for p in candidates if not p.is_file()]
    if missing:
        raise ValueError('Missing release files: '+', '.join(missing))
    if output in candidates:
        raise ValueError('Release output cannot overwrite source files.')
    for path in candidates:
        if path.is_symlink() or path.resolve() != path.absolute() or not path.resolve().is_relative_to(root):
            raise ValueError('Linked files are not allowed in a release.')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"application":"ResearchPilot", "version":__version__, "edition":"local-optional-accounts", "files":{}}
    created = False
    try:
        with output.open('xb') as destination:
            created = True
            with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(candidates):
                    name = path.relative_to(root).as_posix()
                    content = path.read_bytes()
                    manifest['files'][name] = hashlib.sha256(content).hexdigest()
                    entry = zipfile.ZipInfo(name, date_time=(2026,1,1,0,0,0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    bundle.writestr(entry,content)
                bundle.writestr(zipfile.ZipInfo('release-manifest.json',date_time=(2026,1,1,0,0,0)),json.dumps(manifest,ensure_ascii=False,indent=2).encode())
    except BaseException:
        if created: output.unlink(missing_ok=True)
        raise
    with output.open('rb') as source:
        digest=hashlib.file_digest(source,'sha256').hexdigest()
    return {"path":str(output),"sha256":digest,"files":len(manifest['files']),"version":__version__}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts'/'releases'/f'researchpilot-{__version__}-local.zip')
    args=parser.parse_args()
    try:
        result=build_release(ROOT,args.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (OSError,ValueError) as exc:
        parser.exit(1,'Release build failed: '+str(exc)+'\n')
