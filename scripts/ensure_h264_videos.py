"""Encode browser-friendly H.264 MP4 from captured algorithm replay videos."""
import json
from pathlib import Path
import subprocess
import cv2
import imageio_ffmpeg

root=Path(__file__).resolve().parents[1]
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
backup=root/'results/videos/_mpeg4_intermediate'
backup.mkdir(exist_ok=True)
for folder in sorted((root/'results/videos').iterdir()):
    meta=folder/'video_metrics.json'
    target=folder/'full_replay_1x.mp4'
    if not meta.is_file() or not target.is_file():continue
    info=json.loads(meta.read_text(encoding='utf-8'))
    if info.get('codec')=='h264':
        print('SKIP',folder.name,flush=True)
        continue
    temporary=folder/'full_replay_1x.h264.mp4'
    command=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-y',
             '-i',str(target),'-c:v','libx264','-preset','veryfast','-crf','24',
             '-pix_fmt','yuv420p','-movflags','+faststart',str(temporary)]
    subprocess.run(command,check=True,timeout=900)
    v=cv2.VideoCapture(str(temporary))
    frames=int(v.get(cv2.CAP_PROP_FRAME_COUNT))
    fps=float(v.get(cv2.CAP_PROP_FPS))
    opened=v.isOpened()
    v.release()
    if not opened or frames!=info['frames'] or abs(fps-info['fps'])>.01:
        raise RuntimeError(f'H264 re-encoding failed frame verification: {folder.name}')
    original=backup/f'{folder.name}_mpeg4.mp4'
    target.replace(original)
    temporary.replace(target)
    info['codec']='h264'
    info['mpeg4_intermediate']=str(original)
    info['h264_size_bytes']=target.stat().st_size
    meta.write_text(json.dumps(info,indent=2),encoding='utf-8')
    print('PASS',folder.name,frames,'frames',flush=True)
