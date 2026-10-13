"""Pre-publish sanity scan for the FAST-LIVO2 reproduction repository.

    python scripts/preflight_publish.py            # report; exit 1 on blockers
    python scripts/preflight_publish.py --strict   # also fail on legacy/whitelisted hits

Checks
  1. files that git would track but are larger than 50 MB (GitHub hard-blocks 100 MB)
  2. machine-specific absolute paths and local proxy settings inside code files
  3. obvious credentials/tokens
  4. that .gitignore still excludes the heavy directories (data/, wsl/, upstream/,
     .venv-tools/, downloads/, large run artifacts)

Docs and evidence are historical records: absolute paths there are reported as
informational (they do not fail the run) unless --strict is given.
"""
import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ('scripts', 'tests', 'docker', 'configs')
CODE_SUFFIXES = ('.py', '.ps1', '.sh', '.yaml', '.yml', '.json', '.toml')
SIZE_LIMIT_MB = 50

PATH_PATTERNS = [
    re.compile(r'D:\\_AAA', re.I),
    re.compile(r'/mnt/[a-z]/_AAA'),
    re.compile(r'/home/(?!\$|\{)[a-z0-9_]+/repro'),
    re.compile(r'127\.0\.0\.1:7897'),
]
SECRET_PATTERNS = [
    re.compile(r'ghp_[A-Za-z0-9]{20,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    re.compile(r'(?i)(password|passwd|secret)\s*[:=]\s*[\'"][^\'"]{6,}[\'"]'),
]
# files that legitimately contain defaults/legacy markers
WHITELIST = (
    'scripts/site_config.py',
    'scripts/site.ps1',
    'manifests/',
    'docs/',
    'evidence/',
)


def tracked_files():
    try:
        out = subprocess.run(['git', '-c', 'core.quotepath=false', 'ls-files'],
                             cwd=ROOT, capture_output=True, text=True, check=True,
                             encoding='utf-8', errors='replace')
        files = [ROOT / line.strip().strip('"') for line in out.stdout.splitlines() if line.strip()]
        if files:
            return files, 'git ls-files'
    except Exception:
        pass
    skip_dirs = {'.git', 'data', 'wsl', '.venv-tools', 'upstream', 'downloads', 'results', 'evidence'}
    files = [p for p in ROOT.rglob('*')
             if p.is_file() and not any(part in skip_dirs for part in p.relative_to(ROOT).parts)]
    return files, 'filesystem walk (no git index yet)'


def is_whitelisted(rel: str) -> bool:
    return any(rel.startswith(w) for w in WHITELIST)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()

    files, source = tracked_files()
    blockers, warnings, info = [], [], []

    print(f'== preflight: {len(files)} files ({source}) ==')

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        try:
            size_mb = path.stat().st_size / 1e6
        except OSError:
            warnings.append(f'{rel}: cannot stat (odd filename?)')
            continue
        if size_mb > SIZE_LIMIT_MB:
            msg = f'{rel} is {size_mb:.1f} MB (> {SIZE_LIMIT_MB} MB)'
            (warnings if rel.startswith(('docs/', 'evidence/')) else blockers).append(msg)
        if not (path.suffix.lower() in CODE_SUFFIXES or path.name in ('Dockerfile', 'NOTICE')):
            continue
        parts = set(path.relative_to(ROOT).parts)
        if not (parts & set(CODE_DIRS)) and path.parent != ROOT:
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        for pattern in PATH_PATTERNS:
            if pattern.search(text):
                entry = f'{rel}: {pattern.pattern}'
                if is_whitelisted(rel) and not args.strict:
                    info.append(entry)
                elif rel.startswith(CODE_DIRS) or rel.startswith('scripts/'):
                    blockers.append(entry)
                else:
                    warnings.append(entry)
                break
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                blockers.append(f'{rel}: possible secret matching {pattern.pattern}')

    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8') if (ROOT / '.gitignore').exists() else ''
    required = {
        'data/': 'data/',
        'wsl/': 'wsl/',
        'upstream/': 'upstream/',
        '.venv-tools/': '.venv-tools/',
        'downloads/*': 'downloads/*',
        'results/videos/': 'results/videos/',
        'results/runs/**/*.bag': 'results/runs/**/*.bag',
        'results/runs/**/*.pcd': 'results/runs/**/*.pcd',
    }
    missing = [entry for entry, needle in required.items() if needle not in gitignore]
    if missing:
        blockers.append(f'.gitignore misses: {", ".join(missing)}')

    def dump(title, items, limit=25):
        if not items:
            return
        print(f'\n-- {title} ({len(items)}) --')
        for item in items[:limit]:
            print(f'   {item}')
        if len(items) > limit:
            print(f'   ... and {len(items) - limit} more')

    dump('blockers', blockers)
    dump('warnings', warnings)
    dump('informational (historical docs/manifests, config defaults)', info)

    status = 'BLOCKED' if blockers else 'OK'
    print(f'\n== preflight {status}: {len(blockers)} blocker(s), {len(warnings)} warning(s), {len(info)} informational ==')
    return 1 if blockers else 0


if __name__ == '__main__':
    raise SystemExit(main())
