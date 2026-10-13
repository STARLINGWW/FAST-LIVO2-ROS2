"""Produce matched ROS1/ROS2 inputs from the checksum-verified official Hilti bag."""
import hashlib
import argparse
import json
from pathlib import Path
from rosbags.rosbag1 import Reader, Writer as Writer1
from rosbags.rosbag2 import Writer as Writer2
from rosbags.typesys import Stores, get_typestore

root = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--sequence',
                    choices=['exp14_basement_2', 'exp07_long_corridor',
                             'exp18_corridor_lower_gallery_2', 'exp16_attic_to_upper_gallery_2'],
                    default='exp14_basement_2')
parser.add_argument('--tag',default='hilti_exp14')
args=parser.parse_args()
source = root/'data/raw/HILTI22'/f'{args.sequence}.bag'
out = root/'data/derived'
out.mkdir(exist_ok=True)
selected = {'/alphasense/imu', '/alphasense/cam0/image_raw', '/hesai/pandar'}
store = get_typestore(Stores.ROS2_HUMBLE)
store1 = get_typestore(Stores.ROS1_NOETIC)
stats, hashes = {}, {}
with Reader(source) as reader, Writer1(out/f'{args.tag}_3topics.bag') as w1, Writer2(out/f'{args.tag}_ros2', version=8) as w2:
    connections = [c for c in reader.connections if c.topic in selected]
    assert {c.topic for c in connections} == selected
    c1 = {c.id: w1.add_connection(c.topic, c.msgtype, typestore=store1) for c in connections}
    c2 = {c.id: w2.add_connection(c.topic, c.msgtype, typestore=store) for c in connections}
    for c in connections:
        stats[c.topic] = {'expected': c.msgcount, 'messages': 0, 'roundtrip_passed': 0, 'header_backwards': 0}
        hashes[c.topic] = hashlib.sha256()
    for c, t, data in reader.messages(connections=connections):
        cdr = store.ros1_to_cdr(data, c.msgtype)
        back = store.cdr_to_ros1(cdr, c.msgtype)
        # All selected types begin with Header. ROS2 has no Header.seq;
        # every other byte of the reconstructed ROS1 payload must match.
        if bytes(back)[4:] != data[4:]:
            raise ValueError(f'Payload changed beyond Header.seq: {c.topic}, {t}')
        msg = store.deserialize_cdr(cdr, c.msgtype)
        stamp = int(msg.header.stamp.sec)*10**9 + int(msg.header.stamp.nanosec)
        s = stats[c.topic]
        if s['messages'] and stamp < s['last_header_ns']:
            s['header_backwards'] += 1
        s.setdefault('first_header_ns', stamp)
        s['last_header_ns'] = stamp
        s['messages'] += 1
        s['roundtrip_passed'] += 1
        if hasattr(msg, 'encoding'):
            s['image_profile'] = [int(msg.width), int(msg.height), msg.encoding]
        if hasattr(msg, 'fields'):
            s['point_fields'] = [[f.name, f.offset, f.datatype, f.count] for f in msg.fields]
        hashes[c.topic].update(t.to_bytes(8, 'little')); hashes[c.topic].update(data)
        w1.write(c1[c.id], t, data)
        w2.write(c2[c.id], t, cdr)
for topic, s in stats.items():
    assert s['messages'] == s['expected']
    s['source_record_stream_sha256'] = hashes[topic].hexdigest()
report = {'source': str(source), 'topics': stats, 'only_intentional_loss': 'ROS1 Header.seq omitted by ROS2 format',
          'identical_selected_inputs_for_both_algorithms': True}
(root/'results'/f'{args.tag}_conversion_audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
