"""Copy an explicit source/docs allowlist into a local release tree; never publish."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bastion import __version__


def selected_files():
    names=['README.md','architecture.md','ACCEPTANCE.md','RELEASE-0.4.0.md','RELEASE-0.5.0.md','RELEASE-0.6.0.md','RELEASE-0.7.0.md',
        'pyproject.toml','LICENSE','bin/bastion','CONTRIBUTING.md','SECURITY.md','NOTICE.md',
        'tools/docs_demo.py','tools/measure_cli.py','tools/prepare_github.py','tools/render_page.py',
        'tools/qualify_checks.py','tools/qualify_mixed_missions.py','tools/run_repository_task.py']
    files=[ROOT/name for name in names]
    for directory in ('bastion','tests'): files.extend((ROOT/directory).glob('*.py'))
    for directory in ('docs','demo','.github'):
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '.bastion' not in p.parts and '__pycache__' not in p.parts)
    if any(p.is_symlink() or not p.is_file() for p in files): raise RuntimeError('Release inputs must be regular existing files')
    return sorted(set(files))


def stage(destination):
    if destination.exists(): raise RuntimeError('Destination exists; preserve prior evidence and select a new path')
    files=selected_files()
    destination.mkdir(parents=True)
    for source in files:
        target=destination/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    (destination/'.gitignore').write_text((ROOT/'.gitignore').read_text())
    hashes={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob('*')) if p.is_file()}
    manifest={'version':__version__,'stage':'local candidate; publication is a separate action','files':hashes}
    (destination/'PUBLICATION-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=destination.parent/('bastion-'+__version__+'-review.tar.gz')
    if archive.exists(): raise RuntimeError('Archive exists; select a fresh destination parent')
    with tarfile.open(archive,'w:gz') as stream: stream.add(destination,arcname='bastion')
    return {'tree':str(destination),'archive':str(archive),'files':len(hashes),'published':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',default='dist/review-'+__version__)
    args=parser.parse_args();print(json.dumps(stage(Path(args.stage).resolve())))


if __name__=='__main__': main()
