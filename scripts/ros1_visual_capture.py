"""Sample actual ROS1 colored clouds/odometry at 5 Hz without recording full PointCloud2 bags."""
import argparse
from pathlib import Path
import signal
import time
import numpy as np
import rospy
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
    rospy.init_node('fastlivo_visual_capture',anonymous=False,disable_signals=True)
    signal.signal(signal.SIGINT,stop_requested)
    signal.signal(signal.SIGTERM,stop_requested)
    cloud_time=[];cloud_xyz=[];cloud_bgr=[];cloud_count=[]
    odom_time=[];odom_xyz=[]
    last_cloud=None
    interval=int(1e9/args.fps)

    def stamp_ns(t):return int(t.secs)*10**9+int(t.nsecs)

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
        sample=src[ids]
        xyz=np.column_stack([sample[k] for k in ('x','y','z')]).astype(np.float32)
        key='rgb' if 'rgb' in keys else ('rgba' if 'rgba' in keys else None)
        if key:
            bits=sample[key].view(np.uint32)
            bgr=np.column_stack([bits&255,(bits>>8)&255,(bits>>16)&255]).astype(np.uint8)
        else:
            bgr=np.full((len(xyz),3),170,np.uint8)
        valid=np.isfinite(xyz).all(axis=1)
        xyz=xyz[valid];bgr=bgr[valid]
        if not len(xyz):return
        px=np.zeros((args.max_points,3),np.float32)
        pc=np.zeros((args.max_points,3),np.uint8)
        px[:len(xyz)]=xyz
        pc[:len(xyz)]=bgr
        cloud_xyz.append(px);cloud_bgr.append(pc)
        cloud_count.append(len(xyz));cloud_time.append(t);last_cloud=t

    def on_odom(msg):
        odom_time.append(stamp_ns(msg.header.stamp))
        p=msg.pose.pose.position
        odom_xyz.append((p.x,p.y,p.z))

    rospy.Subscriber('/cloud_registered',PointCloud2,on_cloud,queue_size=2,buff_size=8*1024*1024)
    rospy.Subscriber('/aft_mapped_to_init',Odometry,on_odom,queue_size=100)
    while not rospy.is_shutdown() and not stopping:
        time.sleep(.1)
    np.savez_compressed(args.output,
                        cloud_time=np.asarray(cloud_time,np.int64),
                        cloud_xyz=np.asarray(cloud_xyz,np.float32).reshape((-1,args.max_points,3)),
                        cloud_bgr=np.asarray(cloud_bgr,np.uint8).reshape((-1,args.max_points,3)),
                        cloud_count=np.asarray(cloud_count,np.int32),
                        odom_time=np.asarray(odom_time,np.int64),
                        odom_xyz=np.asarray(odom_xyz,np.float32).reshape((-1,3)))
    print('CAPTURE_COMPLETE clouds={} odom={}'.format(len(cloud_time),len(odom_time)),flush=True)
    if len(cloud_time)<10 or len(odom_time)<10:
        raise SystemExit('Insufficient algorithm output for visualization')


if __name__=='__main__':main()
