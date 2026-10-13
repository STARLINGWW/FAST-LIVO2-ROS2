"""One-factor LiDAR ablations on the paper-text configuration (Hilti Exp07).

The paper text fixes voxel 0.5 m, octree layer 3, photometric noise 100 and, for the
PandarXT-32, LiDAR depth/bearing noise 0.001 m / 0.001 deg.  That literal set diverges on
Hilti Exp07 in the released code, while the released HILTI22.yaml keeps the Avia/OS1 noise
pair (0.02 m / 0.05 deg) together with voxel 0.4, max_layer 2 and point_filter_num 1.  These
variants restore exactly one released LiDAR factor at a time (visual keys stay at their
paper values, matching the existing restore_* family) so the divergence driver can be named.
"""
import json
from pathlib import Path
import re
import yaml

root = Path(__file__).resolve().parents[1]
output = root / 'configs/experiments'
paper = yaml.safe_load((output / 'HILTI22_paper_ros1.yaml').read_text(encoding='utf-8'))
released = yaml.safe_load((root / 'upstream/FAST-LIVO2/config/HILTI22.yaml').read_text(encoding='utf-8'))

variants = {
    'noise': (('lio', 'dept_err'), ('lio', 'beam_err')),
    'structure': (('lio', 'voxel_size'), ('lio', 'max_layer')),
    'subsample': (('preprocess', 'point_filter_num'),),
}

double_keys = set()
double_arrays = set()
for file in ('LIVMapper.cpp', 'voxel_map.cpp'):
    cpp = (root / 'ros2/FAST-LIVO2/src' / file).read_text(encoding='utf-8')
    double_keys.update(re.findall(r'declare_parameter<double>\("([^"]+)"', cpp))
    double_arrays.update(re.findall(r'declare_parameter<vector<double>>\("([^"]+)"', cpp))


def cast(node, prefix=''):
    """Match the ROS2 port's declared parameter types (double vs vector<double>)."""
    for key, value in node.items():
        field = f'{prefix}.{key}' if prefix else key
        if isinstance(value, dict):
            cast(value, field)
        elif field in double_keys:
            node[key] = float(value)
        elif field in double_arrays:
            node[key] = [float(x) for x in value]


meta = {}
for name, paths in variants.items():
    cfg = yaml.safe_load(yaml.safe_dump(paper))
    changed = {}
    for section, key in paths:
        released_value = released[section][key]
        changed[f'{section}.{key}'] = {
            'paper_value': paper[section][key],
            'released_value': released_value,
        }
        cfg[section][key] = released_value
    stem = f'HILTI22_paper_{name}_released'
    (output / f'{stem}_ros1.yaml').write_text(yaml.safe_dump(cfg, sort_keys=False), encoding='utf-8')
    cast(cfg)
    (output / f'{stem}_ros2.yaml').write_text(
        yaml.safe_dump({'/**': {'ros__parameters': cfg}}, sort_keys=False), encoding='utf-8')
    meta[name] = {
        'restored_released_lidar_keys': changed,
        'fixed_paper_vio_keys': ['vio.img_point_cov', 'vio.normal_en', 'vio.raycast_en'],
        'run_id': f'abl_l{list(variants).index(name) + 1}_paper_{name}_released_ros1',
    }
(output / 'lidar_ablation_manifest.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
print(json.dumps(meta, indent=2))
