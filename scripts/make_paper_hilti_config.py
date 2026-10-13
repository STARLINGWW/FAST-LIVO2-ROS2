"""Freeze a second Hilti configuration from the explicit settings in FAST-LIVO2 v2.

This is an experiment, not a claim that the paper's entire unpublished config
or official challenge scoring service has been reconstructed.
"""
import json
from pathlib import Path
import re
import yaml

root=Path(__file__).resolve().parents[1]
source=root/'upstream/FAST-LIVO2/config/HILTI22.yaml'
original=yaml.safe_load(source.read_text(encoding='utf-8'))
config=yaml.safe_load(source.read_text(encoding='utf-8'))
changes={
 'preprocess.point_filter_num':3,
 'lio.voxel_size':0.5,
 'lio.max_layer':3,
 'lio.dept_err':0.001,
 'lio.beam_err':0.001,
 'vio.img_point_cov':100.0,
 'vio.normal_en':False,
 'vio.raycast_en':True,
}
for key,value in changes.items():
    group,name=key.split('.')
    config[group][name]=value
destination=root/'configs/experiments'
destination.mkdir(parents=True,exist_ok=True)
ros1=destination/'HILTI22_paper_ros1.yaml'
ros1.write_text(yaml.safe_dump(config,sort_keys=False),encoding='utf-8')
double_keys=set()
double_arrays=set()
for name in ('LIVMapper.cpp','voxel_map.cpp'):
    source_cpp=(root/'ros2/FAST-LIVO2/src'/name).read_text(encoding='utf-8')
    double_keys.update(re.findall(r'declare_parameter<double>\("([^"]+)"',source_cpp))
    double_arrays.update(re.findall(r'declare_parameter<vector<double>>\("([^"]+)"',source_cpp))
def cast_numeric_types(tree,prefix=''):
    for key,value in tree.items():
        field=f'{prefix}.{key}' if prefix else key
        if isinstance(value,dict):cast_numeric_types(value,field)
        elif field in double_keys:tree[key]=float(value)
        elif field in double_arrays:tree[key]=[float(x) for x in value]
cast_numeric_types(config)
ros2=destination/'HILTI22_paper_ros2.yaml'
ros2.write_text(yaml.safe_dump({'/**':{'ros__parameters':config}},sort_keys=False),encoding='utf-8')
diff={key:{'released_config':original[key.split('.')[0]][key.split('.')[1]],'paper_aligned_experiment':value} for key,value in changes.items()}
(destination/'paper_setting_diff.json').write_text(json.dumps(diff,indent=2),encoding='utf-8')
print(json.dumps(diff,indent=2))
