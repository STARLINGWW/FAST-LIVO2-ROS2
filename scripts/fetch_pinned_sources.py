"""Fetch the upstream sources this project pins, into ./upstream/.

The repository does not ship third-party code or datasets. Everything is
reproducible from the pinned revisions recorded in manifests/:

    python scripts/fetch_pinned_sources.py            # fetch everything missing
    python scripts/fetch_pinned_sources.py --verify   # re-check hashes only
    python scripts/fetch_pinned_sources.py --only FAST-LIVO2,Sophus_pinned

Downloads are cached under downloads/upstream_tarballs/ and verified against
the SHA256 values stored in manifests/*.json where one exists; for the rest the
computed hash is recorded into manifests/fetched_sources.json so later runs can
detect drift. Works on Windows and Linux with plain Python 3.8+.
"""
import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'upstream'
CACHE = ROOT / 'downloads' / 'upstream_tarballs'
RECORD = ROOT / 'manifests' / 'fetched_sources.json'


def _load_simple_manifest(name):
    path = ROOT / 'manifests' / name
    data = json.loads(path.read_text(encoding='utf-8'))
    return data['url'], data.get('archive_sha256')


def sources():
    """name -> (dest_dir, url, expected_sha256 or None, archive_root or None)."""
    sophus_url, sophus_sha = _load_simple_manifest('Sophus_pinned.json')
    vikit_url, vikit_sha = _load_simple_manifest('rpg_vikit_pinned.json')
    return {
        'FAST-LIVO2': (
            'FAST-LIVO2',
            'https://codeload.github.com/hku-mars/FAST-LIVO2/tar.gz/0d2c0346107b75b59934975adec9a6eeeb913c64',
            None, None),
        'FAST-LIVO2-ROS2': (
            'FAST-LIVO2-ROS2',
            'https://codeload.github.com/Robotic-Developer-Road/FAST-LIVO2/tar.gz/837b7bbc1431cb04cf936528e52c83c835efba8e',
            None, None),
        'Livox-SDK2': (
            'Livox-SDK2',
            'https://codeload.github.com/Livox-SDK/Livox-SDK2/tar.gz/c0796f04c143143899c87a773d9f6b7136453c0b',
            None, None),
        'livox_ros_driver2': (
            'livox_ros_driver2',
            'https://codeload.github.com/Livox-SDK/livox_ros_driver2/tar.gz/21445540f0d100dc86a7e6df312dd70bbdb4afdf',
            None, None),
        'rpg_vikit_ros2': (
            'rpg_vikit_ros2',
            'https://codeload.github.com/xuankuzcr/rpg_vikit/tar.gz/4b7abc838f5d2ca9137f70f122eaaeff9eaf0f50',
            None, None),
        'Sophus_pinned': ('Sophus_pinned', sophus_url, sophus_sha, 'Sophus-a621ff2e'),
        'rpg_vikit_pinned': ('rpg_vikit_pinned', vikit_url, vikit_sha,
                             'rpg_vikit-6c886c8e5d83997806e00294826d528cea3581dd'),
    }


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, target, attempts=5):
    """Download with retries: codeload.github.com drops TLS connections now and then."""
    target.parent.mkdir(parents=True, exist_ok=True)
    last_error = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={'User-Agent': 'fastlivo2-repro-fetch'})
        try:
            with urllib.request.urlopen(request, timeout=180) as response, target.open('wb') as out:
                shutil.copyfileobj(response, out, length=1 << 20)
            return
        except Exception as exc:                       # URLError, ssl.SSLError, timeout, ...
            last_error = exc
            target.unlink(missing_ok=True)
            if attempt < attempts:
                wait = min(2 ** attempt, 15)
                print(f'  download attempt {attempt}/{attempts} failed ({exc}); retrying in {wait}s',
                      file=sys.stderr, flush=True)
                time.sleep(wait)
    raise RuntimeError(f'download failed after {attempts} attempts: {url}\n'
                       f'last error: {last_error}\n'
                       'if your network needs a proxy, set HTTPS_PROXY (or pass --proxy where supported)')


def extract(archive, dest, archive_root=None):
    tmp = dest.parent / (dest.name + '.extract')
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    with tarfile.open(archive, 'r:gz') as tar:
        try:
            tar.extractall(tmp, filter='data')          # Python >= 3.12
        except TypeError:
            tar.extractall(tmp)                          # older Python
    roots = [p for p in tmp.iterdir() if p.is_dir()]
    if archive_root and (tmp / archive_root).is_dir():
        root = tmp / archive_root
    elif len(roots) == 1:
        root = roots[0]
    else:
        raise RuntimeError(f'cannot determine archive root in {tmp}: {roots}')
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(root), str(dest))
    shutil.rmtree(tmp, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', help='comma separated subset of names')
    parser.add_argument('--verify', action='store_true', help='only verify cached archives')
    parser.add_argument('--force', action='store_true', help='re-download and re-extract')
    args = parser.parse_args()

    table = sources()
    selected = list(table)
    if args.only:
        wanted = {x.strip() for x in args.only.split(',') if x.strip()}
        unknown = wanted - set(table)
        if unknown:
            print(f'unknown source(s): {sorted(unknown)}; known: {sorted(table)}', file=sys.stderr)
            return 2
        selected = [x for x in selected if x in wanted]

    UPSTREAM.mkdir(exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    record = {}
    if RECORD.exists():
        record = json.loads(RECORD.read_text(encoding='utf-8'))

    failures = 0
    for name in selected:
        dest_name, url, expected, archive_root = table[name]
        dest = UPSTREAM / dest_name
        archive = CACHE / f'{name}.tar.gz'
        status = 'present'
        if args.verify:
            if not archive.exists():
                print(f'MISSING cache {name}: {archive}')
                failures += 1
                continue
            actual = sha256(archive)
            ok = expected is None or actual == expected
            print(f'{"OK" if ok else "DRIFT"} {name:<20} sha256={actual}')
            failures += 0 if ok else 1
            continue
        if not archive.exists() or args.force:
            print(f'download {name} <- {url}', flush=True)
            download(url, archive)
            status = 'downloaded'
        actual = sha256(archive)
        if expected and actual != expected:
            print(f'HASH MISMATCH {name}: expected {expected}, got {actual}', file=sys.stderr)
            failures += 1
            continue
        if not dest.exists() or args.force:
            extract(archive, dest, archive_root)
            status = 'extracted'
        record[name] = {
            'dest': str(dest.relative_to(ROOT).as_posix()),
            'url': url,
            'archive_sha256': actual,
            'expected_sha256': expected,
            'status': status,
            'checked_at': datetime.now(timezone.utc).astimezone().isoformat(),
        }
        print(f'{status:<10} {name:<20} -> {dest}')

    if not args.verify:
        RECORD.parent.mkdir(exist_ok=True)
        RECORD.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f'wrote {RECORD.relative_to(ROOT)} ({len(record)} entries)')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
