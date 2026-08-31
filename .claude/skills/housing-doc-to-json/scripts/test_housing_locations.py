#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib.util
import math
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("housing_locations.py")
SPEC = importlib.util.spec_from_file_location("housing_locations", MODULE_PATH)
housing_locations = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(housing_locations)


class HousingLocationsTest(unittest.TestCase):
    def test_coordinate_round_trip(self):
        latitude, longitude = 25.05436, 121.564
        x, y = housing_locations.wgs84_to_twd97(latitude, longitude)
        actual_lat, actual_lng = housing_locations.twd97_to_wgs84(x, y)
        self.assertTrue(math.isclose(latitude, actual_lat, abs_tol=1e-7))
        self.assertTrue(math.isclose(longitude, actual_lng, abs_tol=1e-7))

    def test_full_width_doorplate_is_normalized(self):
        row = {
            "街路段": "三民路", "地區": "", "巷": "", "弄": "", "號": "９１號"
        }
        self.assertEqual(
            housing_locations.doorplate_address(row, "松山區"),
            "臺北市松山區三民路91號",
        )

    def test_floor_level_doorplate_is_ignored(self):
        row = {
            "街路段": "三民路", "地區": "", "巷": "", "弄": "", "號": "91號二樓"
        }
        self.assertEqual(housing_locations.doorplate_address(row, "松山區"), "")
        self.assertEqual(
            housing_locations.doorplate_base_address(row, "松山區"),
            "臺北市松山區三民路91號",
        )

    def test_official_address_classification(self):
        self.assertEqual(
            housing_locations.official_address("健康路285號", "松山區"),
            ("臺北市松山區健康路285號", "exact"),
        )
        self.assertEqual(
            housing_locations.official_address("朱崙街與朱崙街27巷交叉口", "中山區"),
            ("臺北市中山區朱崙街與朱崙街27巷交叉口", "intersection"),
        )
        self.assertEqual(
            housing_locations.official_address("福德段二小段319地號", "信義區"),
            ("", ""),
        )

    def test_selection_excludes_non_locations(self):
        rows = [
            {"name": "測試社宅", "distict": "文山區", "houseHolds": "10"},
            {"name": "行政中心", "distict": "信義區", "houseHolds": "0"},
            {"name": "外縣市", "distict": "新店區", "houseHolds": "10"},
            {"name": "民辦都更(56處)", "distict": "大同區", "houseHolds": "3611"},
        ]
        self.assertEqual([row["name"] for row in housing_locations.select_projects(rows)], ["測試社宅"])


if __name__ == "__main__":
    unittest.main()
