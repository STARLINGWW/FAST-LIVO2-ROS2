"""Compare independent Retail runs using the same fixed-scale pose metric."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

root=Path(__file__).resolve().parents[1]
cases={
 'ros1_internal':['retail_ros1_1x_01','retail_ros1_1x_02','retail_ros1_1x_03'],
 'ros2_internal':['retail_ros2_1x_01','retail_ros2_1x_02','retail_ros2_1x_03'],
 'cross_implementation':['retail_ros1_1x_01','retail_ros2_1x_01','retail_ros2_1x_02','retail_ros2_1x_03']
}
output=root/'results/aggregated/repeatability'
output.mkdir(parents=True,exist_ok=True)
result={}
for label,runs in cases.items():
    ref=root/'results/runs'/runs[0]/'trajectory.tum'
    pairs=[]
    for name in runs[1:]:
        path=output/f'{label}_{name}'
        trajectory=root/'results/runs'/name/'trajectory.tum'
        cmd=[sys.executable,str(root/'scripts/evaluate_trajectories.py'),str(ref),str(trajectory),
             '--reference-kind','ros1_baseline','--output',str(path)]
        subprocess.run(cmd,stdout=subprocess.DEVNULL,check=True)
        metric=json.loads((path/'metrics.json').read_text())
        pairs.append({'reference':runs[0],'estimate':name,'aligned_rmse_m':metric['aligned_rmse_m'],
                      'matched_rows':metric['matched_rows'],'estimate_association_fraction':metric['estimate_association_fraction']})
    vals=np.asarray([x['aligned_rmse_m'] for x in pairs])
    result[label]={'pairs':pairs,'mean_rmse_m':float(vals.mean()),
                   'std_rmse_m':float(vals.std(ddof=1)) if len(vals)>1 else None,
                   'max_rmse_m':float(vals.max())}
(output/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
