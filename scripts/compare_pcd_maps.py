"""Quantify cross-implementation agreement between two estimated maps."""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from render_pcd_map import open_pcd, sample_cloud


def summary(x):
    return {'median_m':float(np.median(x)), 'p95_m':float(np.percentile(x,95)),
            'rmse_m':float(np.sqrt(np.mean(np.square(x)))),
            'within_10cm_fraction':float(np.mean(x<=.1))}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('ros1_pcd',type=Path)
    p.add_argument('ros2_pcd',type=Path)
    p.add_argument('trajectory_metrics',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--sample-limit',type=int,default=80000)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    a,meta1=open_pcd(args.ros1_pcd)
    b,meta2=open_pcd(args.ros2_pcd)
    xyz1,c1,_=sample_cloud(a,args.sample_limit)
    xyz2,c2,_=sample_cloud(b,args.sample_limit)
    pose=json.loads(args.trajectory_metrics.read_text())
    rotation=np.asarray(pose['alignment_rotation'])
    translation=np.asarray(pose['alignment_translation'])
    xyz2=(xyz2@rotation.T)+translation
    tree1,tree2=cKDTree(xyz1),cKDTree(xyz2)
    d21,i21=tree1.query(xyz2,k=1,workers=4)
    d12,i12=tree2.query(xyz1,k=1,workers=4)
    close=d21<=.1
    color=np.abs(c2[close].astype(float)-c1[i21[close]].astype(float)).mean(axis=1) if close.any() else []
    result={'label':'ROS1/ROS2 estimated-map agreement, not map-to-survey ground truth',
            'alignment':'SE3 from run-specific odometry, no scale',
            'ros1_full_points':meta1['points'],'ros2_full_points':meta2['points'],
            'ros1_sample_points':len(xyz1),'ros2_sample_points':len(xyz2),
            'ros2_to_ros1_nearest':summary(d21), 'ros1_to_ros2_nearest':summary(d12),
            'matched_within_10cm_color_abs_mean_0_to_255':float(np.mean(color)) if len(color) else None}
    (args.output/'map_comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    keep1=np.linspace(0,len(xyz1)-1,min(20000,len(xyz1)),dtype=int)
    keep2=np.linspace(0,len(xyz2)-1,min(20000,len(xyz2)),dtype=int)
    fig,ax=plt.subplots(figsize=(10,7),constrained_layout=True)
    ax.scatter(xyz1[keep1,0],xyz1[keep1,1],s=.3,c='royalblue',alpha=.4,label='ROS1')
    ax.scatter(xyz2[keep2,0],xyz2[keep2,1],s=.3,c='darkorange',alpha=.4,label='ROS2 aligned')
    ax.axis('equal');ax.set(xlabel='x [m]',ylabel='y [m]',title='Estimated map overlap');ax.legend()
    fig.savefig(args.output/'map_overlap.png',dpi=170)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
