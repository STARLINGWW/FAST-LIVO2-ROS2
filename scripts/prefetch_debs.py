"""Prefetch failed public apt artifacts; apt still verifies package indexes/hashes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import time
import requests

root = Path(__file__).resolve().parents[1]
manifest = root/'manifests/noetic_debs_prefetch.json'
if manifest.exists():
    urls = sorted({x['url'] for x in json.loads(manifest.read_text(encoding='utf-8')) if x.get('url')})
else:
    log = (root/'results/build_ros1_aliyun.log').read_text(encoding='utf-8')
    urls = sorted(set(re.findall(r'E: Failed to fetch (https?://\S+\.deb)', log)))
folder = root/'downloads/noetic_debs'
folder.mkdir(parents=True, exist_ok=True)


def fetch(url):
    filename = url.rsplit('/', 1)[1]
    path = folder/filename
    if path.exists():
        return {'file': filename, 'url': url, 'status': 'cached', 'bytes': path.stat().st_size}
    source = url
    session = requests.Session()
    session.trust_env = False
    for attempt in range(3):
        try:
            with session.get(source, stream=True, timeout=(15, 35)) as response:
                response.raise_for_status()
                partial = path.with_suffix('.deb.partial')
                with partial.open('wb') as f:
                    for chunk in response.iter_content(256*1024):
                        f.write(chunk)
                if partial.read_bytes()[:8] != b'!<arch>\n':
                    raise ValueError('Response is not a Debian archive')
                partial.replace(path)
            return {'file': filename, 'url': source, 'status': 'downloaded', 'bytes': path.stat().st_size}
        except Exception as exc:
            error = str(exc)
            time.sleep(1)
    return {'file': filename, 'url': source, 'status': 'failed', 'error': error}


results = []
print(json.dumps({'requested_packages': len(urls)}), flush=True)
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [executor.submit(fetch, url) for url in urls]
    for future in as_completed(futures):
        results.append(future.result())
        if len(results) % 25 == 0:
            print(json.dumps({'completed': len(results), 'failed': sum(x['status']=='failed' for x in results)}), flush=True)
(root/'manifests/noetic_debs_prefetch.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps({'completed': len(results), 'failed': sum(x['status']=='failed' for x in results)}), flush=True)
