"""Inspect native FAST-LIVO2 PCD; export a reproducible map preview and PLY."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def open_pcd(path):
    fields = {}
    with path.open('rb') as f:
        while True:
            line = f.readline()
            if not line:
                raise ValueError('PCD header has no DATA line')
            decoded = line.decode('ascii', errors='replace').strip()
            if decoded.startswith('DATA '):
                if decoded != 'DATA binary':
                    raise ValueError(f'Expected native binary PCD: {decoded}')
                offset = f.tell()
                break
            key, _, value = decoded.partition(' ')
            fields[key] = value.split()
    names = fields['FIELDS']
    sizes = list(map(int, fields['SIZE']))
    types = fields['TYPE']
    counts = list(map(int, fields.get('COUNT', ['1']*len(names))))
    formats = []
    for size, typ, count in zip(sizes, types, counts):
        kind = {'F':'f', 'I':'i', 'U':'u'}[typ]
        fmt = np.dtype('<' + kind + str(size))
        formats.append(fmt if count == 1 else (fmt, (count,)))
    dtype = np.dtype(list(zip(names, formats)))
    n = int(fields['POINTS'][0])
    available = path.stat().st_size - offset
    if available < n*dtype.itemsize:
        raise ValueError(f'Truncated PCD: {available} data bytes for {n} points')
    cloud = np.memmap(path, dtype=dtype, mode='r', offset=offset, shape=(n,))
    return cloud, {'points': n, 'fields': names, 'point_bytes': dtype.itemsize,
                   'data_bytes': available, 'binary_bytes_expected': n*dtype.itemsize}


def sample_cloud(cloud, count):
    ids = np.linspace(0, len(cloud)-1, min(count, len(cloud)), dtype=np.int64)
    sample = cloud[ids]
    xyz = np.column_stack([sample[k] for k in ('x','y','z')]).astype(np.float32)
    if 'rgb' in cloud.dtype.names:
        rgb = sample['rgb'].view(np.uint32)
        color = np.column_stack([(rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255]).astype(np.uint8)
    elif all(x in cloud.dtype.names for x in ('r','g','b')):
        color = np.column_stack([sample[k] for k in ('r','g','b')]).astype(np.uint8)
    else:
        c = sample['intensity'] if 'intensity' in cloud.dtype.names else xyz[:,2]
        c = np.asarray(c, dtype=float)
        v = np.clip((c-np.percentile(c,2))/(np.percentile(c,98)-np.percentile(c,2)+1e-6),0,1)
        color = (plt.cm.viridis(v)[:,:3]*255).astype(np.uint8)
    mask = np.isfinite(xyz).all(axis=1)
    return xyz[mask], color[mask], len(mask)-int(mask.sum())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('pcd', type=Path)
    p.add_argument('--trajectory', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sample-limit', type=int, default=400000)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cloud, meta = open_pcd(args.pcd)
    xyz, color, nonfinite = sample_cloud(cloud, args.sample_limit)
    if len(xyz) < 1000:
        raise ValueError('Map has fewer than 1000 finite sampled points')
    occupied = np.unique(np.floor(xyz/0.10).astype(np.int32), axis=0)
    meta.update({'sampled_points':len(xyz), 'sampled_nonfinite':nonfinite,
                 'occupied_10cm_voxels_in_sample':len(occupied),
                 'bbox_min_m':xyz.min(0).tolist(), 'bbox_max_m':xyz.max(0).tolist(),
                 'xyz_p01_m':np.percentile(xyz,1,axis=0).tolist(),
                 'xyz_p99_m':np.percentile(xyz,99,axis=0).tolist(),
                 'mean_rgb':color.mean(0).tolist(),
                 'non_grayscale_sample_fraction':float(np.mean(np.ptp(color.astype(np.int16),axis=1)>10))})
    traj = np.loadtxt(args.trajectory, ndmin=2) if args.trajectory else None
    ids = np.linspace(0,len(xyz)-1,min(len(xyz),100000),dtype=np.int64)
    pts = xyz[ids]; colors=color[ids]/255.
    fig=plt.figure(figsize=(14,6),constrained_layout=True)
    ax=fig.add_subplot(121)
    ax.scatter(pts[:,0],pts[:,1],c=colors,s=.2,linewidths=0,rasterized=True)
    if traj is not None:
        ax.plot(traj[:,1],traj[:,2],color='deepskyblue',lw=1.2,label='odometry')
        ax.legend(loc='upper right')
    ax.set(xlabel='x [m]',ylabel='y [m]',title='Top-down color map');ax.axis('equal');ax.grid(alpha=.2)
    ax3=fig.add_subplot(122,projection='3d')
    ax3.scatter(pts[:,0],pts[:,1],pts[:,2],c=colors,s=.15,linewidths=0,rasterized=True)
    ax3.set(xlabel='x [m]',ylabel='y [m]',zlabel='z [m]',title='3D map');ax3.view_init(elev=25,azim=-65)
    fig.savefig(args.output/'map_overview.png',dpi=160)
    if traj is not None:
        low=traj[:,1:3].min(axis=0)-15
        high=traj[:,1:3].max(axis=0)+15
        near=(xyz[:,0]>=low[0])&(xyz[:,0]<=high[0])&(xyz[:,1]>=low[1])&(xyz[:,1]<=high[1])
        local=xyz[near]
        local_color=color[near]/255.
        if len(local)>1000:
            subset=np.linspace(0,len(local)-1,min(len(local),100000),dtype=int)
            local=local[subset];local_color=local_color[subset]
            detail=plt.figure(figsize=(14,6),constrained_layout=True)
            near_ax=detail.add_subplot(121)
            near_ax.scatter(local[:,0],local[:,1],c=local_color,s=.35,linewidths=0,rasterized=True)
            near_ax.plot(traj[:,1],traj[:,2],color='deepskyblue',lw=1.3)
            near_ax.set(xlabel='x [m]',ylabel='y [m]',title='Map around trajectory');near_ax.axis('equal');near_ax.grid(alpha=.2)
            tilted=detail.add_subplot(122,projection='3d')
            tilted.scatter(local[:,0],local[:,1],local[:,2],c=local_color,s=.25,linewidths=0,rasterized=True)
            tilted.set(xlabel='x [m]',ylabel='y [m]',zlabel='z [m]',title='Local 3D detail')
            tilted.view_init(elev=28,azim=-65)
            detail.savefig(args.output/'map_detail.png',dpi=160)
            meta['local_preview_points']=len(local)
    ply=args.output/'preview_sample.ply'
    with ply.open('wb') as f:
        header=(f'ply\nformat binary_little_endian 1.0\nelement vertex {len(xyz)}\n'
                'property float x\nproperty float y\nproperty float z\n'
                'property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
        f.write(header.encode('ascii'))
        binary=np.empty(len(xyz),dtype=[('x','<f4'),('y','<f4'),('z','<f4'),('r','u1'),('g','u1'),('b','u1')])
        for i,key in enumerate(('x','y','z')):binary[key]=xyz[:,i]
        for i,key in enumerate(('r','g','b')):binary[key]=color[:,i]
        binary.tofile(f)
    (args.output/'map_metrics.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps(meta,indent=2))


if __name__=='__main__':
    main()
