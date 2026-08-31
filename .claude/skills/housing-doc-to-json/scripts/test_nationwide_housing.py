#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("nationwide_housing.py")
SPEC = importlib.util.spec_from_file_location("nationwide_housing", MODULE_PATH)
nationwide = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nationwide)


class NationwideHousingTest(unittest.TestCase):
    def test_moi_parser_and_exclusions(self):
        html = """
        <table id="t3"><tbody>
          <tr><td>台南市</td><td>新市安居</td><td>中央(住都中心)</td>
          <td>1,000</td><td>113/1/1</td><td>113/2/1</td><td>116/1/1</td><td>新完工</td></tr>
          <tr><td>臺南市</td><td>國產署包租案件-第1批</td><td>中央</td>
          <td>5</td><td>-</td><td>-</td><td>-</td><td>新完工</td></tr>
        </tbody></table>
        """
        rows = nationwide.parse_moi_html(html)
        self.assertEqual(rows[0]["county"], "臺南市")
        self.assertEqual(rows[0]["households"], 1000)
        self.assertEqual(rows[0]["status"], "已完工")
        self.assertIsNone(rows[0]["excluded_reason"])
        self.assertIsNotNone(rows[1]["excluded_reason"])

    def test_normalization_and_stable_identifiers(self):
        self.assertEqual(nationwide.normalize_text("台東縣 臺東市"), "臺東縣臺東市")
        self.assertEqual(
            nationwide.normalize_name("興隆社會住宅 I 區"),
            nationwide.normalize_name("興隆I區社宅"),
        )
        first = nationwide.stable_id("高雄市", "福山安居", "中央(住都中心)")
        second = nationwide.stable_id("高雄市", " 福山安居 ", "中央(住都中心)")
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("tw-"))

    def test_resolve_from_nhurc(self):
        row = {
            "county": "高雄市", "name": "福山安居", "organizer": "中央(住都中心)",
            "households": 441, "status": "已完工", "official_status": "新完工",
        }
        detail = {
            ("高雄市", nationwide.normalize_name("福山安居")): {
                "district": "左營區", "address": "高雄市左營區華夏路1558號",
                "floors": "地上14層，地下2層", "map": "!2d120.319!3d22.688",
                "source_url": "https://www.socialhousing.tw/example",
            }
        }
        item, problem = nationwide.resolve_project(row, {"aliases": {}, "projects": {}}, detail, {})
        self.assertIsNone(problem)
        self.assertEqual(item["address_precision"], "exact")
        self.assertEqual(item["district"], "左營區")
        self.assertEqual(item["latitude"], 22.688)
        self.assertEqual(item["longitude"], 120.319)

    def test_unresolved_project_is_not_published(self):
        row = {
            "county": "花蓮縣", "name": "某段123地號基地", "organizer": "花蓮縣政府",
            "households": 50, "status": "規劃中", "official_status": "規劃中",
        }
        item, problem = nationwide.resolve_project(row, {"aliases": {}, "projects": {}}, {}, {})
        self.assertIsNone(item)
        self.assertEqual(problem["reason"], "missing verified navigable address")

    def test_generated_indexes_are_consistent(self):
        item = {
            "id": "tw-test", "name": "福山安居", "county": "高雄市", "district": "左營區",
            "address": "高雄市左營區華夏路1558號", "address_precision": "exact",
            "address_method": "official_address", "address_distance_m": None,
            "official_location": None, "latitude": 22.688, "longitude": 120.319,
            "households": 441, "residents": None, "floors": "地上14層，地下2層",
            "status": "已完工", "official_status": "新完工", "project_type": "中央興辦",
            "organizer": "中央(住都中心)", "source_urls": ["https://example.gov.tw/project"],
            "updated_at": None,
        }
        original_root = nationwide.API_ROOT
        try:
            with tempfile.TemporaryDirectory() as temporary:
                nationwide.API_ROOT = Path(temporary) / "v2"
                docs = nationwide.api_documents([item], {"discovered": 1, "excluded": 0, "selected": 1})
                for path, document in docs.items():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(nationwide.json_text(document), encoding="utf-8")
                self.assertEqual(nationwide.validate_api(nationwide.API_ROOT), [])
                regions = json.loads((nationwide.API_ROOT / "regions.json").read_text(encoding="utf-8"))
                self.assertEqual(len(regions["regions"]), 22)
                kaohsiung = next(row for row in regions["regions"] if row["name"] == "高雄市")
                self.assertEqual(kaohsiung["count"], 1)
        finally:
            nationwide.API_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
