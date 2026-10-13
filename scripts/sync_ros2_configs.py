"""Translate official ROS1 YAML to ROS2 namespace and declared numeric types.

Values are preserved; overrides used by experiments belong in their run folders.
"""
import json
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
double_keys, double_arrays = set(), set()
for name in ('LIVMapper.cpp', 'voxel_map.cpp'):
    source = (ROOT / 'ros2/FAST-LIVO2/src' / name).read_text(encoding='utf-8')
    double_keys.update(re.findall(r'declare_parameter<double>\("([^"]+)"', source))
    double_arrays.update(re.findall(r'declare_parameter<vector<double>>\("([^"]+)"', source))


def cast_tree(tree, prefix=''):
    for key, value in tree.items():
        path = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            cast_tree(value, path)
        elif path in double_keys:
            tree[key] = float(value)
        elif path in double_arrays:
            tree[key] = [float(x) for x in value]


audit = []
for path in sorted((ROOT / 'upstream/FAST-LIVO2/config').glob('*.yaml')):
    original = yaml.safe_load(path.read_text(encoding='utf-8'))
    tree = yaml.safe_load(path.read_text(encoding='utf-8'))
    cast_tree(tree)
    assert tree == original, f'Unexpected value change in {path.name}'
    out = ROOT / 'ros2/FAST-LIVO2/config' / path.name
    out.write_text(yaml.safe_dump({'/**': {'ros__parameters': tree}}, sort_keys=False), encoding='utf-8')
    audit.append({'config': path.name, 'values_equal_to_official': True})
(ROOT / 'manifests/config_equivalence.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
print(json.dumps(audit))
