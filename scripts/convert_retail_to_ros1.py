"""Reconstruct a ROS1 replay bag from the documented public ROS2 mirror.

This does not claim to recover the original file checksum. Each message must
survive a CDR -> ROS1 -> CDR round trip with identical semantic content.
"""
import argparse
import dataclasses
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from rosbags.rosbag1 import Writer
from rosbags.rosbag2 import Reader
from rosbags.typesys import Stores, get_typestore, get_types_from_msg


def same(a, b):
    if dataclasses.is_dataclass(a):
        return all(same(getattr(a, f.name), getattr(b, f.name))
                   for f in dataclasses.fields(a) if f.name != '__msgtype__')
    if isinstance(a, np.ndarray):
        return np.array_equal(a, b, equal_nan=True)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--messages', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    src_store, dst_store = get_typestore(Stores.ROS2_HUMBLE), get_typestore(Stores.ROS1_NOETIC)
    for namespace in ('livox_ros_driver', 'livox_ros_driver2'):
        definitions = {}
        for name in ('CustomPoint', 'CustomMsg'):
            text = (args.messages / f'{name}.msg').read_text().replace('livox_ros_driver2/', namespace + '/')
            definitions.update(get_types_from_msg(text, f'{namespace}/msg/{name}'))
        src_store.register(definitions)
        dst_store.register(definitions)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    topics = defaultdict(lambda: {'messages': 0, 'byte_exact_roundtrips': 0,
                                 'semantic_roundtrips': 0, 'header_backwards': 0})
    stream_hashes = defaultdict(hashlib.sha256)
    with Reader(args.source) as reader, Writer(args.destination) as writer:
        connections = {}
        for c in reader.connections:
            target = c.msgtype.replace('livox_ros_driver2/', 'livox_ros_driver/')
            connections[c.id] = writer.add_connection(c.topic, target, typestore=dst_store)
            topics[c.topic]['source_type'] = c.msgtype
            topics[c.topic]['target_type'] = target
            topics[c.topic]['expected_messages'] = c.msgcount
        for c, stamp, raw in reader.messages():
            wire = src_store.cdr_to_ros1(raw, c.msgtype)
            back = src_store.ros1_to_cdr(wire, c.msgtype)
            decoded = src_store.deserialize_cdr(raw, c.msgtype)
            stats = topics[c.topic]
            if bytes(back) == bytes(raw):
                stats['byte_exact_roundtrips'] += 1
            elif same(decoded, src_store.deserialize_cdr(back, c.msgtype)):
                stats['semantic_roundtrips'] += 1
            else:
                raise ValueError(f'Roundtrip changed message: {c.topic} at {stamp}')
            hstamp = int(decoded.header.stamp.sec) * 10**9 + int(decoded.header.stamp.nanosec)
            if stats['messages'] and hstamp < stats['last_header_ns']:
                stats['header_backwards'] += 1
            stats.setdefault('first_record_ns', stamp)
            stats.setdefault('first_header_ns', hstamp)
            stats['last_record_ns'], stats['last_header_ns'] = stamp, hstamp
            stats['messages'] += 1
            if hasattr(decoded, 'points'):
                if decoded.point_num != len(decoded.points):
                    raise ValueError('point_num disagrees with points array')
                stats['total_points'] = stats.get('total_points', 0) + len(decoded.points)
            if hasattr(decoded, 'encoding'):
                stats['image_profile'] = [int(decoded.width), int(decoded.height), decoded.encoding]
            stream_hashes[c.topic].update(stamp.to_bytes(8, 'little'))
            stream_hashes[c.topic].update(raw)
            writer.write(connections[c.id], stamp, wire)
    for topic, stats in topics.items():
        if stats['messages'] != stats['expected_messages']:
            raise ValueError(f'Message count changed: {topic}')
        stats['source_record_stream_sha256'] = stream_hashes[topic].hexdigest()
    report = {'source': str(args.source), 'destination': str(args.destination),
              'origin': 'DeepRoboticsLab public ROS2 Retail_Street mirror; original ROS1 download quota exceeded',
              'all_message_roundtrips_passed': True, 'topics': dict(topics)}
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
