"""Render a 1x-duration video from recorded algorithm outputs and original images.

The run itself is executed and recorded at 1x; encoding occurs afterwards.
Frames show only sensor and map output available by that simulated timestamp.
"""
import argparse
import json
from pathlib import Path
from contextlib import nullcontext
import cv2
import numpy as np
from rosbags.rosbag1 import Reader as Reader1
from rosbags.rosbag2 import Reader as Reader2
from rosbags.typesys import Stores, get_typestore
from render_pcd_map import open_pcd, sample_cloud


def stamp_ns(stamp):
    return int(stamp.sec)*10**9+int(stamp.nanosec)


def decode_image(msg):
    channels = 1 if msg.encoding in ('mono8','8UC1') else 3
    data = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.step)
    arr = data[:, :msg.width*channels].reshape(msg.height,msg.width,channels)
    if channels == 1:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if msg.encoding == 'rgb8':
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    if msg.encoding == 'bgr8':
        return arr.copy()
    raise ValueError(f'Unsupported image encoding: {msg.encoding}')


def cloud_points(msg, cap=8000):
    if msg.width * msg.height == 0 or msg.point_step == 0:
        return np.empty((0,3),np.float32),np.empty((0,3),np.uint8)
    specs = {f.name:f for f in msg.fields}
    keys = [k for k in ('x','y','z','rgb','rgba') if k in specs]
    if not all(k in keys for k in ('x','y','z')):
        raise ValueError('Registered cloud has no XYZ coordinates')
    formats = ['<f4' if specs[k].datatype == 7 else '<u4' for k in keys]
    dtype = np.dtype({'names':keys,'formats':formats,
                      'offsets':[specs[k].offset for k in keys], 'itemsize':msg.point_step})
    n=msg.width*msg.height
    data = np.frombuffer(msg.data,dtype=dtype,count=n)
    sampled=data[np.linspace(0,n-1,min(n,cap),dtype=np.int64)]
    xyz=np.column_stack([sampled[k] for k in ('x','y','z')]).astype(np.float32)
    key='rgb' if 'rgb' in keys else ('rgba' if 'rgba' in keys else None)
    if key:
        packed=sampled[key].view(np.uint32)
        rgb=np.column_stack([(packed>>16)&255,(packed>>8)&255,packed&255]).astype(np.uint8)
        bgr=rgb[:,::-1]
    else:
        bgr=np.full((len(xyz),3),170,dtype=np.uint8)
    good=np.isfinite(xyz).all(axis=1)
    return xyz[good],bgr[good]


def project(xyz, bounds, width, height):
    lo,hi=bounds
    norm=(xyz[:,:2]-lo[:2])/(hi[:2]-lo[:2]+1e-6)
    col=(norm[:,0]*(width-1)).astype(np.int32)
    row=((1-norm[:,1])*(height-1)).astype(np.int32)
    mask=(col>=0)&(col<width)&(row>=0)&(row<height)
    return col[mask],row[mask],mask


def fit_panel(frame, shape):
    w,h=shape
    frame=cv2.resize(frame,(w,h),interpolation=cv2.INTER_AREA)
    return frame


def recorded_events(path, reader, decoder, kind):
    if path.suffix.lower()=='.npz':
        with np.load(path,allow_pickle=False) as saved:
            cloud_t=saved['cloud_time'];odom_t=saved['odom_time']
            cloud_xyz=saved['cloud_xyz'];cloud_bgr=saved['cloud_bgr'];counts=saved['cloud_count']
            odom_xyz=saved['odom_xyz']
            i=j=0
            while i<len(cloud_t) or j<len(odom_t):
                if i<len(cloud_t) and (j>=len(odom_t) or cloud_t[i]<=odom_t[j]):
                    yield 'cloud',int(cloud_t[i]),(cloud_xyz[i,:counts[i]],cloud_bgr[i,:counts[i]])
                    i+=1
                else:
                    yield 'odom',int(odom_t[j]),odom_xyz[j]
                    j+=1
        return
    conns=[c for c in reader.connections if c.topic in ('/cloud_registered','/aft_mapped_to_init')]
    for connection,_,payload in reader.messages(connections=conns):
        msg=(decoder.deserialize_ros1(payload,connection.msgtype) if kind=='ros1'
             else decoder.deserialize_cdr(payload,connection.msgtype))
        when=stamp_ns(msg.header.stamp)
        if connection.topic=='/cloud_registered':
            yield 'cloud',when,cloud_points(msg)
        else:
            p=msg.pose.pose.position
            yield 'odom',when,np.array([p.x,p.y,p.z],dtype=np.float32)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('input_bag',type=Path)
    p.add_argument('recorded_output',type=Path)
    p.add_argument('map_pcd',type=Path)
    p.add_argument('--trajectory',type=Path)
    p.add_argument('--image-topic',required=True)
    p.add_argument('--format',choices=['ros1','ros2'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fps',type=int,default=5)
    args=p.parse_args()
    if args.fps<1 or args.fps>30:
        raise ValueError('FPS outside 1..30')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    cloud,meta=open_pcd(args.map_pcd)
    sampled,_,_=sample_cloud(cloud,100000)
    if args.trajectory:
        path=np.loadtxt(args.trajectory,ndmin=2)
        lower=sampled.min(axis=0);upper=sampled.max(axis=0)
        lower[:2]=path[:,1:3].min(axis=0)-20
        upper[:2]=path[:,1:3].max(axis=0)+20
    else:
        lower=np.percentile(sampled,0.5,axis=0)
        upper=np.percentile(sampled,99.5,axis=0)
    padding=np.maximum((upper-lower)*.07,1.0)
    bounds=(lower-padding,upper+padding)
    first=0
    writer=cv2.VideoWriter(str(args.output),cv2.VideoWriter_fourcc(*'mp4v'),args.fps,(1280,720))
    if not writer.isOpened():raise RuntimeError('MPEG4 video encoder unavailable')
    decoder_in=get_typestore(Stores.ROS1_NOETIC)
    decoder_out=get_typestore(Stores.ROS1_NOETIC if args.format=='ros1' else Stores.ROS2_HUMBLE)
    output_reader=(None if args.recorded_output.suffix.lower()=='.npz' else
                   (Reader1(args.recorded_output) if args.format=='ros1' else Reader2(args.recorded_output)))
    framecount=cloudcount=odomcount=0
    try:
        with Reader1(args.input_bag) as source, (output_reader or nullcontext(None)) as record:
            first=source.start_time
            input_connection=[c for c in source.connections if c.topic==args.image_topic]
            if len(input_connection)!=1:raise ValueError('Expected one source image connection')
            images=iter(source.messages(connections=input_connection))
            next_image=next(images,None)
            camera=np.zeros((360,640,3),dtype=np.uint8)
            map_panel=np.full((360,900,3),18,dtype=np.uint8)
            scan_panel=np.full((360,640,3),18,dtype=np.uint8)
            last_pose=None
            next_frame=first
            interval=int(1e9/args.fps)
            for event,when,payload in recorded_events(args.recorded_output,record,decoder_out,args.format):
                if when<first-1_000_000_000:continue
                while next_image is not None and next_image[1]<=when:
                    camera=fit_panel(decode_image(decoder_in.deserialize_ros1(next_image[2],next_image[0].msgtype)),(640,360))
                    next_image=next(images,None)
                if event=='cloud':
                    xyz,bgr=payload
                    if len(xyz)==0:
                        continue
                    scan_panel[:]=18
                    scan_low=np.percentile(xyz,1,axis=0)
                    scan_high=np.percentile(xyz,99,axis=0)
                    scan_pad=np.maximum((scan_high-scan_low)*.08,0.5)
                    col,row,keep=project(xyz,(scan_low-scan_pad,scan_high+scan_pad),640,360)
                    scan_panel[row,col]=bgr[keep]
                    cm,rm,keepmap=project(xyz,bounds,900,360)
                    map_panel[rm,cm]=bgr[keepmap]
                    cloudcount+=1
                else:
                    xyz=np.asarray(payload,dtype=np.float32).reshape(1,3)
                    col,row,keep=project(xyz,bounds,900,360)
                    if keep.any():
                        new_pose=(int(col[0]),int(row[0]))
                        if last_pose is not None:cv2.line(map_panel,last_pose,new_pose,(255,210,20),2)
                        last_pose=new_pose
                    odomcount+=1
                while when>=next_frame:
                    t=(next_frame-first)/1e9
                    canvas=np.full((720,1280,3),20,dtype=np.uint8)
                    canvas[:360,:640]=camera
                    canvas[:360,640:]=scan_panel
                    canvas[360:,:900]=map_panel
                    cv2.putText(canvas,'SOURCE CAMERA',(14,29),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
                    cv2.putText(canvas,'REGISTERED POINTS',(653,29),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
                    cv2.putText(canvas,'GROWING WORLD MAP + TRAJECTORY',(14,390),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2)
                    cv2.putText(canvas,f'Sensor time: +{t:06.1f} s',(913,420),cv2.FONT_HERSHEY_SIMPLEX,.65,(235,235,235),1)
                    cv2.putText(canvas,f'Clouds: {cloudcount}',(913,455),cv2.FONT_HERSHEY_SIMPLEX,.65,(235,235,235),1)
                    cv2.putText(canvas,f'Odom: {odomcount}',(913,490),cv2.FONT_HERSHEY_SIMPLEX,.65,(235,235,235),1)
                    cv2.putText(canvas,'1x recorded replay',(913,536),cv2.FONT_HERSHEY_SIMPLEX,.63,(130,225,255),1)
                    cv2.putText(canvas,'Video rendered after run',(913,567),cv2.FONT_HERSHEY_SIMPLEX,.50,(180,180,180),1)
                    writer.write(canvas)
                    framecount+=1
                    next_frame+=interval
    finally:
        writer.release()
    duration=framecount/args.fps
    result={'video':str(args.output),'frames':framecount,'fps':args.fps,'video_duration_s':duration,
            'registered_cloud_messages':cloudcount,'odometry_messages':odomcount,
            'recorded_output':str(args.recorded_output),'map_pcd':str(args.map_pcd),
            'rendering':'1x time axis from recorded 1x ROS output; encoded offline'}
    if cloudcount<10 or odomcount<10 or duration<10:
        raise RuntimeError(f'Insufficient visual output: {result}')
    (args.output.parent/'video_metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
