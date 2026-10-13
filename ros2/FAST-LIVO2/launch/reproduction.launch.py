"""Offline launcher: local calibration, simulated time, no FCU output."""
import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    configs = os.path.join(get_package_share_directory('fast_livo'), 'config')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=os.path.join(configs, 'avia.yaml')),
        DeclareLaunchArgument('camera', default_value=os.path.join(configs, 'camera_pinhole.yaml')),
        DeclareLaunchArgument('sequence', default_value='retail_ros2'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('image_enabled', default_value='1'),
        Node(package='fast_livo', executable='fastlivo_mapping', name='laserMapping',
             output='screen', parameters=[
                 LaunchConfiguration('config'), LaunchConfiguration('camera'),
                 {'use_sim_time': ParameterValue(LaunchConfiguration('use_sim_time'), value_type=bool),
                  'evo.pose_output_en': True,
                  'evo.seq_name': LaunchConfiguration('sequence'),
                  'common.img_en': ParameterValue(LaunchConfiguration('image_enabled'), value_type=int),
                  'pcd_save.pcd_save_en': False,
                  'image_save.img_save_en': False}],
             remappings=[('/mavros/vision_pose/pose', '/fastlivo2/raw_vision_pose')])
    ])
