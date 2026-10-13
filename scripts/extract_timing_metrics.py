"""Parse per-frame LIO/VIO processing times printed by FAST-LIVO2."""
import argparse
import csv
import json
from pathlib import Path
import re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ansi = re.compile(r'\x1b\[[0-9;]*m')
total_line = re.compile(r'\|\s+Current Total Time\s+\|\s+([0-9.]+)\s+\|')


def parse(path):
    values = {'LIO': [], 'VIO': []}
    state = None
    for raw in path.open(encoding='utf-8', errors='replace'):
        line = ansi.sub('', raw)
        if 'LIO Mapping Time' in line:
            state = 'LIO'
        match = total_line.search(line)
        if match and state in values:
            values[state].append(float(match.group(1)) * 1000)
            state = 'VIO' if state == 'LIO' else None
    return values


def describe(a):
    if not a:
        return None
    v = np.asarray(a)
    return {'frames': len(v), 'mean_ms': float(v.mean()), 'median_ms': float(np.median(v)),
            'p95_ms': float(np.percentile(v, 95)), 'p99_ms': float(np.percentile(v, 99)),
            'max_ms': float(v.max()), 'over_100ms': int((v > 100).sum())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    source = args.run/'algorithm.log'
    data = parse(source)
    summary = {name: describe(vals) for name, vals in data.items()}
    (args.run/'timing_metrics.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with (args.run/'timing_frames.csv').open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['module', 'frame_index', 'process_ms'])
        for name, vals in data.items():
            for i, v in enumerate(vals):
                w.writerow([name, i, v])
    fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    for name, vals in data.items():
        if vals:
            ax.plot(np.arange(len(vals)), vals, label=f'{name} ({len(vals)} frames)', alpha=.65, linewidth=.65)
    ax.set(xlabel='Frame index', ylabel='Processing time [ms]', title=args.run.name)
    ax.set_ylim(0, min(250, max([np.percentile(v, 99.5) for v in data.values() if v] or [50]) * 1.15))
    ax.grid(alpha=.3); ax.legend()
    fig.savefig(args.run/'timing_frames.png', dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
