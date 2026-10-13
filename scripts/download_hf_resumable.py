"""Download a public Hugging Face file using checked HTTP byte ranges."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import requests


def main():
    p = argparse.ArgumentParser()
    p.add_argument('url')
    p.add_argument('destination', type=Path)
    p.add_argument('expected_sha256')
    # No proxy is assumed. Pass --proxy or set HTTPS_PROXY when your network needs one.
    p.add_argument('--proxy', default=os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or '')
    args = p.parse_args()
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    proxy = {'http': args.proxy, 'https': args.proxy} if args.proxy else None
    total = None
    for attempt in range(1, 41):
        size = args.destination.stat().st_size if args.destination.exists() else 0
        if total is not None and size == total:
            break
        headers = {'Range': f'bytes={size}-'} if size else {}
        try:
            with requests.get(args.url, headers=headers, proxies=proxy,
                              timeout=(25, 60), stream=True) as response:
                response.raise_for_status()
                if size:
                    content_range = response.headers.get('Content-Range', '')
                    if response.status_code != 206 or not content_range.startswith(f'bytes {size}-'):
                        raise RuntimeError(f'Server did not honor resume from {size}: {response.status_code} {content_range}')
                    total = int(content_range.rsplit('/', 1)[1])
                else:
                    total = int(response.headers.get('Content-Length', 0)) or None
                printed_at = time.monotonic()
                with args.destination.open('ab' if size else 'wb') as out:
                    for block in response.iter_content(4 * 1024 * 1024):
                        out.write(block)
                        size += len(block)
                        if time.monotonic() - printed_at > 15:
                            out.flush()
                            print(json.dumps({'attempt':attempt,'bytes':size,'total':total}),flush=True)
                            printed_at = time.monotonic()
        except (requests.RequestException, RuntimeError) as exc:
            print(json.dumps({'attempt':attempt,'bytes':size,'error':str(exc)[:250]}),flush=True)
            if 'did not honor resume' in str(exc):
                raise
            time.sleep(min(attempt*2, 15))
            continue
        if total is not None and size == total:
            break
    actual = args.destination.stat().st_size
    if total is None or actual != total:
        raise RuntimeError(f'Incomplete file: {actual} of {total} bytes')
    with args.destination.open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    if digest.lower() != args.expected_sha256.lower():
        raise RuntimeError(f'SHA256 mismatch: {digest}')
    print(json.dumps({'path':str(args.destination),'bytes':actual,'sha256':digest,'verified':True}),flush=True)


if __name__ == '__main__':
    main()
