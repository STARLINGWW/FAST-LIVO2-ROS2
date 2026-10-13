"""Download a publicly shared file using its normal confirmation form, with timeouts.

Never bypasses a quota/login page. Partial files are resumed only when the server
honours the exact requested Content-Range. Progress and failures go to stdout.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


def main():
    p = argparse.ArgumentParser()
    p.add_argument('id')
    p.add_argument('output', type=Path)
    p.add_argument('--proxy')
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    part = args.output.with_suffix(args.output.suffix + '.partial')
    session = requests.Session()
    if args.proxy:
        session.proxies.update(http=args.proxy, https=args.proxy)
    url = 'https://drive.usercontent.google.com/download'
    params = {'id': args.id, 'export': 'download'}
    for attempt in range(1, 6):
        try:
            offset = part.stat().st_size if part.exists() else 0
            headers = {'Range': f'bytes={offset}-'} if offset else {}
            with session.get(url, params=params, headers=headers, stream=True,
                             timeout=(20, 60)) as first:
                first.raise_for_status()
                if 'text/html' in first.headers.get('Content-Type', ''):
                    soup = BeautifulSoup(first.text, 'html.parser')
                    form = soup.find('form', id='download-form')
                    if form is None:
                        raise RuntimeError(soup.get_text(' ', strip=True)[:500])
                    url = urljoin(first.url, form['action'])
                    params = {x['name']: x.get('value', '') for x in form.find_all('input') if x.get('name')}
                else:
                    raise RuntimeError('Expected confirmation form before download')
            print(json.dumps({'attempt': attempt, 'resume_bytes': offset}), flush=True)
            with session.get(url, params=params, headers=headers, stream=True,
                             timeout=(20, 60)) as response:
                response.raise_for_status()
                if 'text/html' in response.headers.get('Content-Type', ''):
                    raise RuntimeError('Download returned HTML; quota or authentication must be resolved at source')
                if offset and (response.status_code != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')):
                    raise RuntimeError('Server did not honour resume range; retaining partial file')
                expected = int(response.headers.get('Content-Length', 0)) or None
                received = 0
                last = time.monotonic()
                with part.open('ab' if offset else 'wb') as out:
                    for block in response.iter_content(1024 * 1024):
                        out.write(block)
                        received += len(block)
                        if time.monotonic() - last >= 15:
                            out.flush()
                            print(json.dumps({'bytes': offset + received, 'remaining_response': None if expected is None else expected - received}), flush=True)
                            last = time.monotonic()
                if expected is not None and received != expected:
                    raise RuntimeError('Truncated response')
            part.replace(args.output)
            digest = hashlib.file_digest(args.output.open('rb'), 'sha256').hexdigest()
            print(json.dumps({'completed': str(args.output), 'bytes': args.output.stat().st_size, 'sha256': digest}), flush=True)
            return
        except (requests.RequestException, RuntimeError) as exc:
            print(json.dumps({'attempt': attempt, 'error': str(exc)}), flush=True)
            # Retrieve a fresh normal confirmation form on retry.
            url = 'https://drive.usercontent.google.com/download'
            params = {'id': args.id, 'export': 'download'}
            if 'quota' in str(exc).lower() or 'Too many users' in str(exc):
                raise
            if attempt == 5:
                raise
            time.sleep(3)


if __name__ == '__main__':
    main()
