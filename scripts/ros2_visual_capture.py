"""Low-bandwidth recorder for real ROS2 map/odometry publications.

Samples a bounded number of world points at 5 Hz, preserving message times.
BEST_EFFORT point-cloud QoS prevents this display recorder from blocking SLAM.
"""
import argparse
from pathlib import Path
import signal
import time
import numpy as np
import rclpy
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import PointCloud2
from nav_msgs.msg import Odometry

stopping=False


def stop_requested(_number, _frame):
    global stopping
    stopping=True


def main():
    p=argparse.ArgumentParser()
    p.add_argument('output',type=Path)
    p.add_argument('--max-points',type=int,default=5000)
    p.add_argument('--fps',type=int,default=5)
    args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    rclpy.init()
    signal.signal(signal.SIGINT,stop_requested)
    signal.signal(signal.SIGTERM,stop_requested)
    node=rclpy.create_node('fastlivo_visual_capture')
    cloud_time=[]; cloud_xyz=[]; cloud_bgr=[]; cloud_count=[]
    odom_time=[]; odom_xyz=[]
    last_cloud=None
    interval=int(1e9/args.fps)

    def stamp_ns(s):return int(s.sec)*10**9+int(s.nanosec)

    def on_cloud(msg):
        nonlocal last_cloud
        t=stamp_ns(msg.header.stamp)
        if msg.width*msg.height==0 or not msg.fields or msg.point_step==0:return
        if last_cloud is not None and t-last_cloud<interval:return
        specs={f.name:f for f in msg.fields}
        if not all(k in specs for k in ('x','y','z')):return
        keys=[k for k in ('x','y','z','rgb','rgba') if k in specs]
        dtype=np.dtype({'names':keys,
                        'formats':['<f4' if specs[k].datatype==7 else '<u4' for k in keys],
                        'offsets':[specs[k].offset for k in keys],
                        'itemsize':msg.point_step})
        n=msg.width*msg.height
        src=np.frombuffer(msg.data,dtype=dtype,count=n)
        ids=np.linspace(0,n-1,min(n,args.max_points),dtype=np.int64)
        points=src[ids]
        xyz=np.column_stack([points[k] for k in ('x','y','z')]).astype(np.float32)
        color_key='rgb' if 'rgb' in keys else ('rgba' if 'rgba' in keys else None)
        if color_key:
            bits=points[color_key].view(np.uint32)
            bgr=np.column_stack([bits&255,(bits>>8)&255,(bits>>16)&255]).astype(np.uint8)
        else:
            bgr=np.full((len(xyz),3),170,np.uint8)
        valid=np.isfinite(xyz).all(axis=1)
        xyz=xyz[valid];bgr=bgr[valid]
        if not len(xyz):return
        padded_xyz=np.zeros((args.max_points,3),dtype=np.float32)
        padded_bgr=np.zeros((args.max_points,3),dtype=np.uint8)
        padded_xyz[:len(xyz)]=xyz
        padded_bgr[:len(xyz)]=bgr
        cloud_xyz.append(padded_xyz);cloud_bgr.append(padded_bgr)
        cloud_count.append(len(xyz));cloud_time.append(t);last_cloud=t

    def on_odom(msg):
        odom_time.append(stamp_ns(msg.header.stamp))
        p=msg.pose.pose.position
        odom_xyz.append((p.x,p.y,p.z))

    qos=QoSProfile(history=HistoryPolicy.KEEP_LAST,depth=5,reliability=ReliabilityPolicy.BEST_EFFORT)
    node.create_subscription(PointCloud2,'/cloud_registered',on_cloud,qos)
    node.create_subscription(Odometry,'/aft_mapped_to_init',on_odom,10)
    try:
        while rclpy.ok() and not stopping:
            rclpy.spin_once(node,timeout_sec=.1)
    finally:
        np.savez_compressed(args.output,
                            cloud_time=np.asarray(cloud_time,dtype=np.int64),
                            cloud_xyz=np.asarray(cloud_xyz,dtype=np.float32).reshape((-1,args.max_points,3)),
                            cloud_bgr=np.asarray(cloud_bgr,dtype=np.uint8).reshape((-1,args.max_points,3)),
                            cloud_count=np.asarray(cloud_count,dtype=np.int32),
                            odom_time=np.asarray(odom_time,dtype=np.int64),
                            odom_xyz=np.asarray(odom_xyz,dtype=np.float32).reshape((-1,3)))
        print(f'CAPTURE_COMPLETE clouds={len(cloud_time)} odom={len(odom_time)}',flush=True)
        node.destroy_node()
        rclpy.shutdown()
    if len(cloud_time)<10 or len(odom_time)<10:
        raise SystemExit('Insufficient algorithm output for visualization')


if __name__=='__main__':main()
