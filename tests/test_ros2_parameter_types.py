"""The paper variant must survive ROS2's strict numeric parameter typing."""
import re
import unittest
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]


class ParameterTypeTests(unittest.TestCase):
    def test_paper_ros2_matches_ros1_values_and_declared_double_types(self):
        ros1=yaml.safe_load((ROOT/'configs/experiments/HILTI22_paper_ros1.yaml').read_text())
        ros2=yaml.safe_load((ROOT/'configs/experiments/HILTI22_paper_ros2.yaml').read_text())['/**']['ros__parameters']
        self.assertEqual(ros1,ros2)
        keys=set();arrays=set()
        for file in ('LIVMapper.cpp','voxel_map.cpp'):
            cpp=(ROOT/'ros2/FAST-LIVO2/src'/file).read_text(encoding='utf-8')
            keys.update(re.findall(r'declare_parameter<double>\("([^"]+)"',cpp))
            arrays.update(re.findall(r'declare_parameter<vector<double>>\("([^"]+)"',cpp))
        for path in keys:
            group,key=path.split('.',1)
            if group in ros2 and key in ros2[group]:
                self.assertIsInstance(ros2[group][key],float,path)
        for path in arrays:
            group,key=path.split('.',1)
            if group in ros2 and key in ros2[group]:
                self.assertTrue(all(isinstance(v,float) for v in ros2[group][key]),path)


if __name__=='__main__':unittest.main()
