"""Controlled one-factor visual variants on the documented paper LiDAR setup."""
import json
from pathlib import Path
import re
import yaml

root=Path(__file__).resolve().parents[1]
output=root/'configs/experiments'
paper=yaml.safe_load((output/'HILTI22_paper_ros1.yaml').read_text(encoding='utf-8'))
released=yaml.safe_load((root/'upstream/FAST-LIVO2/config/HILTI22.yaml').read_text(encoding='utf-8'))
keys=('img_point_cov','normal_en','raycast_en')
variants={
 'release_vio': keys,
 'restore_cov': ('img_point_cov',),
 'restore_normal': ('normal_en',),
 'restore_raycast': ('raycast_en',),
}
double_keys=set();double_arrays=set()
for file in ('LIVMapper.cpp','voxel_map.cpp'):
    cpp=(root/'ros2/FAST-LIVO2/src'/file).read_text(encoding='utf-8')
    double_keys.update(re.findall(r'declare_parameter<double>\("([^"]+)"',cpp))
    double_arrays.update(re.findall(r'declare_parameter<vector<double>>\("([^"]+)"',cpp))
def cast(node,prefix=''):
    for key,value in node.items():
        field=f'{prefix}.{key}' if prefix else key
        if isinstance(value,dict):cast(value,field)
        elif field in double_keys:node[key]=float(value)
        elif field in double_arrays:node[key]=[float(x) for x in value]
meta={}
for name,restored in variants.items():
    cfg=yaml.safe_load(yaml.safe_dump(paper))
    for key in restored:cfg['vio'][key]=released['vio'][key]
    stem=f'HILTI22_paper_lidar_{name}'
    (output/f'{stem}_ros1.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False),encoding='utf-8')
    cast(cfg)
    (output/f'{stem}_ros2.yaml').write_text(yaml.safe_dump({'/**':{'ros__parameters':cfg}},sort_keys=False),encoding='utf-8')
    meta[name]={'restored_vio_keys':list(restored),'fixed_paper_lidar_keys':
                ['preprocess.point_filter_num','lio.voxel_size','lio.max_layer','lio.dept_err','lio.beam_err']}
(output/'vio_sensitivity_manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
print(json.dumps(meta,indent=2))
