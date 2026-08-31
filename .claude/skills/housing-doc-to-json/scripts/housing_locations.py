#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and validate the versioned Taipei social-housing location API."""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
API_ROOT = REPO / "api/v1"
DISTRICT_ROOT = API_ROOT / "districts"
OVERRIDES = REPO / ".claude/skills/housing-doc-to-json/batch/housing_address_overrides.json"
HOUSING_API_URL = "https://hms.udd.gov.taipei/api/BigData/project"
HOUSING_DATASET_URL = (
    "https://data.taipei/dataset/detail?id=659c3565-df41-4f80-915f-95e83071bdcd"
)
DOORPLATE_URL = (
    "https://data.taipei/api/frontstage/tpeod/dataset/resource.download?"
    "rid=ce76ca0c-7f94-4935-ab47-1d2a41ca2abb"
)
DOORPLATE_DATASET_URL = (
    "https://data.taipei/dataset/detail?id=b7c8e724-1e98-45ee-a0bd-f3840623ed97"
)
MAX_NEARBY_METERS = 250.0
MIN_SOURCE_RATIO = 0.90

DISTRICTS = {
    "中正區": ("zhongzheng", "63000050"),
    "大同區": ("datong", "63000060"),
    "中山區": ("zhongshan", "63000040"),
    "松山區": ("songshan", "63000010"),
    "大安區": ("daan", "63000030"),
    "萬華區": ("wanhua", "63000070"),
    "信義區": ("xinyi", "63000020"),
    "士林區": ("shilin", "63000110"),
    "北投區": ("beitou", "63000120"),
    "內湖區": ("neihu", "63000100"),
    "南港區": ("nangang", "63000090"),
    "文山區": ("wenshan", "63000080"),
}
DISTRICT_BY_CODE = {code: name for name, (_, code) in DISTRICTS.items()}
EXCLUDED_NAMES = {"民辦都更(56處)", "公辦都更(28處)"}
REQUIRED_ITEM_KEYS = {
    "id", "name", "city", "district", "address", "address_precision",
    "address_method", "address_distance_m", "official_location",
    "address_source_url", "latitude", "longitude", "households", "residents",
    "floors", "status",
}


def normalize_text(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace("台北市", "臺北市")
    return re.sub(r"\s+", "", value).strip()


def nullable_int(value):
    text = normalize_text(value)
    return int(text.replace(",", "")) if text else None


def nullable_float(value):
    text = normalize_text(value)
    return float(text) if text and text != "0" else None


def canonical_address(value, district):
    address = normalize_text(value)
    if not address:
        return ""
    if address.startswith(district):
        return "臺北市" + address
    if address.startswith("臺北市"):
        if district not in address[:12]:
            return "臺北市" + district + address[3:]
        return address
    return "臺北市" + district + address


def official_address(value, district):
    address = canonical_address(value, district)
    if re.search(r"\d+(?:[-之]\d+)?號", address):
        return address, "exact"
    if any(token in address for token in ("交叉口", "路口", "巷口")):
        return address, "intersection"
    return "", ""


def stable_id(district, name):
    key = f"{normalize_text(district)}\0{normalize_text(name)}".encode("utf-8")
    return "taipei-" + hashlib.sha256(key).hexdigest()[:16]


def wgs84_to_twd97(latitude, longitude):
    """Convert WGS84 coordinates to TWD97 TM2 zone 121."""
    a = 6378137.0
    b = 6356752.314245
    k0 = 0.9999
    dx = 250000.0
    lon0 = math.radians(121.0)
    e = 1 - (b * b) / (a * a)
    ep = e / (1 - e)
    lat = math.radians(latitude)
    lon = math.radians(longitude)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    n = a / math.sqrt(1 - e * sin_lat * sin_lat)
    t = math.tan(lat) ** 2
    c = ep * cos_lat * cos_lat
    aa = cos_lat * (lon - lon0)
    m = a * (
        (1 - e / 4 - 3 * e**2 / 64 - 5 * e**3 / 256) * lat
        - (3 * e / 8 + 3 * e**2 / 32 + 45 * e**3 / 1024) * math.sin(2 * lat)
        + (15 * e**2 / 256 + 45 * e**3 / 1024) * math.sin(4 * lat)
        - (35 * e**3 / 3072) * math.sin(6 * lat)
    )
    x = dx + k0 * n * (
        aa + (1 - t + c) * aa**3 / 6
        + (5 - 18 * t + t**2 + 72 * c - 58 * ep) * aa**5 / 120
    )
    y = k0 * (
        m + n * math.tan(lat) * (
            aa**2 / 2 + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * ep) * aa**6 / 720
        )
    )
    return x, y


def twd97_to_wgs84(x, y):
    """Convert TWD97 TM2 zone 121 coordinates to WGS84."""
    a = 6378137.0
    b = 6356752.314245
    k0 = 0.9999
    dx = 250000.0
    lon0 = math.radians(121.0)
    e = 1 - (b * b) / (a * a)
    ep = e / (1 - e)
    m = y / k0
    mu = m / (a * (1 - e / 4 - 3 * e**2 / 64 - 5 * e**3 / 256))
    e1 = (1 - math.sqrt(1 - e)) / (1 + math.sqrt(1 - e))
    fp = (
        mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    sin_fp = math.sin(fp)
    cos_fp = math.cos(fp)
    t1 = math.tan(fp) ** 2
    c1 = ep * cos_fp**2
    n1 = a / math.sqrt(1 - e * sin_fp**2)
    r1 = a * (1 - e) / (1 - e * sin_fp**2) ** 1.5
    d = (x - dx) / (n1 * k0)
    lat = fp - (n1 * math.tan(fp) / r1) * (
        d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep - 3 * c1**2) * d**6 / 720
    )
    lon = lon0 + (
        d - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep + 24 * t1**2) * d**5 / 120
    ) / cos_fp
    return math.degrees(lat), math.degrees(lon)


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    command = [
        "curl", "--fail", "--location", "--silent", "--show-error",
        "--retry", "3", "--retry-delay", "2", "--output", str(temporary), url,
    ]
    try:
        subprocess.run(command, check=True)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def source_path(value, destination, refresh=False):
    if value:
        return Path(value)
    if refresh or not destination.exists():
        return download(HOUSING_API_URL if destination.suffix == ".json" else DOORPLATE_URL, destination)
    return destination


def load_source(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("housing source must be a JSON array")
    return data


def select_projects(rows):
    selected = []
    for row in rows:
        name = normalize_text(row.get("name"))
        district = normalize_text(row.get("distict"))
        households = nullable_int(row.get("houseHolds")) or 0
        if district not in DISTRICTS or households <= 0 or name in EXCLUDED_NAMES:
            continue
        selected.append({**row, "name": name, "distict": district})
    selected.sort(key=lambda row: (DISTRICTS[row["distict"]][0], row["name"]))
    return selected


def doorplate_address(row, district):
    number = normalize_text(row.get("號"))
    if not number or "樓" in number or "地下" in number:
        return ""
    parts = [row.get(key, "") for key in ("街路段", "地區", "巷", "弄", "號")]
    body = "".join(normalize_text(part) for part in parts)
    return canonical_address(body, district) if body else ""


def doorplate_base_address(row, district):
    """Return the building-level address even when a CSV row names a floor."""
    number = normalize_text(row.get("號"))
    match = re.match(r"(.+?號)", number)
    if not match:
        return ""
    parts = [row.get(key, "") for key in ("街路段", "地區", "巷", "弄")]
    body = "".join(normalize_text(part) for part in parts) + match.group(1)
    return canonical_address(body, district)


def match_doorplates(projects, doorplate_path, overrides):
    targets = defaultdict(list)
    override_addresses = defaultdict(list)
    for project in projects:
        lat = nullable_float(project.get("lat"))
        lng = nullable_float(project.get("lng"))
        if lat is not None and lng is not None:
            x, y = wgs84_to_twd97(lat, lng)
            targets[project["distict"]].append((project, x, y))
        key = f'{project["distict"]}/{project["name"]}'
        override = overrides.get(key)
        if override:
            lookup = normalize_text(override["address"]).removesuffix("附近")
            override_addresses[project["distict"]].append((key, lookup))

    nearest = {}
    override_coordinates = {}
    with open(doorplate_path, encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            district = DISTRICT_BY_CODE.get(normalize_text(row.get("鄉鎮市區代碼")))
            if not district or (district not in targets and district not in override_addresses):
                continue
            try:
                x = float(row["橫座標"])
                y = float(row["縱座標"])
            except (KeyError, TypeError, ValueError):
                continue
            address = doorplate_address(row, district)
            base_address = address or doorplate_base_address(row, district)
            normalized = normalize_text(base_address)
            for key, lookup in override_addresses[district]:
                if normalized == lookup and key not in override_coordinates:
                    override_coordinates[key] = twd97_to_wgs84(x, y)
            if not address:
                continue
            for project, target_x, target_y in targets[district]:
                key = f'{project["distict"]}/{project["name"]}'
                distance2 = (x - target_x) ** 2 + (y - target_y) ** 2
                if key not in nearest or distance2 < nearest[key][0]:
                    nearest[key] = (distance2, address)
    return nearest, override_coordinates


def build_items(projects, nearest, override_coordinates, overrides):
    items = []
    for row in projects:
        district = row["distict"]
        name = row["name"]
        key = f"{district}/{name}"
        original = normalize_text(row.get("address"))
        lat = nullable_float(row.get("lat"))
        lng = nullable_float(row.get("lng"))
        override = overrides.get(key)
        direct_address, precision = official_address(original, district)

        if override:
            address = normalize_text(override["address"])
            precision = override["address_precision"]
            method = "curated_official"
            distance = override.get("address_distance_m")
            source_url = override["source_url"]
            if (lat is None or lng is None) and key in override_coordinates:
                lat, lng = override_coordinates[key]
        elif direct_address:
            address = direct_address
            method = "official_housing"
            distance = 0.0
            source_url = HOUSING_API_URL
        else:
            if key not in nearest:
                raise ValueError(f"{key}: no doorplate match")
            distance2, address = nearest[key]
            distance = round(math.sqrt(distance2), 1)
            if distance > MAX_NEARBY_METERS:
                raise ValueError(f"{key}: nearest doorplate is {distance} m away")
            precision = "nearby"
            method = "nearest_doorplate"
            source_url = DOORPLATE_DATASET_URL

        item = {
            "id": stable_id(district, name),
            "name": name,
            "city": "臺北市",
            "district": district,
            "address": address,
            "address_precision": precision,
            "address_method": method,
            "address_distance_m": distance,
            "official_location": original or None,
            "address_source_url": source_url,
            "latitude": round(lat, 6) if lat is not None else None,
            "longitude": round(lng, 6) if lng is not None else None,
            "households": nullable_int(row.get("houseHolds")),
            "residents": nullable_int(row.get("persons")),
            "floors": normalize_text(row.get("floors")) or None,
            "status": normalize_text(row.get("progress")),
        }
        items.append(item)
    return items


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def existing_timestamp(items):
    path = API_ROOT / "housing-locations.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("items") == items:
                return existing.get("updated_at")
        except Exception:
            pass
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def api_documents(items):
    updated_at = existing_timestamp(items)
    source = {
        "dataset_url": HOUSING_DATASET_URL,
        "api_url": HOUSING_API_URL,
        "doorplate_dataset_url": DOORPLATE_DATASET_URL,
    }
    common = {"schema_version": "1.0", "updated_at": updated_at, "source": source}
    documents = {
        API_ROOT / "housing-locations.json": {**common, "count": len(items), "items": items},
    }
    district_rows = []
    for district, (code, _) in DISTRICTS.items():
        district_items = [item for item in items if item["district"] == district]
        path = f"districts/{code}.json"
        district_rows.append({"code": code, "name": district, "count": len(district_items), "path": path})
        documents[DISTRICT_ROOT / f"{code}.json"] = {
            **common, "district": district, "district_code": code,
            "count": len(district_items), "items": district_items,
        }
    documents[API_ROOT / "districts.json"] = {
        **common, "count": len(district_rows), "districts": district_rows,
    }
    documents[API_ROOT / "index.json"] = {
        **common,
        "housing_count": len(items),
        "district_count": len(district_rows),
        "endpoints": {
            "all": "housing-locations.json",
            "districts": "districts.json",
            "district": "districts/{district-code}.json",
        },
    }
    return documents


def write_documents(documents):
    for path, document in documents.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json_text(document)
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")


def validate_api(api_root=API_ROOT):
    errors = []
    try:
        all_doc = json.loads((api_root / "housing-locations.json").read_text(encoding="utf-8"))
        district_doc = json.loads((api_root / "districts.json").read_text(encoding="utf-8"))
        index_doc = json.loads((api_root / "index.json").read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"API files cannot be loaded: {exc}"]
    items = all_doc.get("items", [])
    if all_doc.get("count") != len(items):
        errors.append("housing-locations count does not match items")
    if index_doc.get("housing_count") != len(items):
        errors.append("index housing_count does not match items")
    ids = set()
    names = set()
    for item in items:
        missing = REQUIRED_ITEM_KEYS - set(item)
        if missing:
            errors.append(f"{item.get('name', '<unknown>')}: missing {sorted(missing)}")
            continue
        key = (item["district"], item["name"])
        if item["id"] in ids:
            errors.append(f"{item['name']}: duplicate id")
        if key in names:
            errors.append(f"{item['name']}: duplicate district/name")
        ids.add(item["id"])
        names.add(key)
        if item["district"] not in DISTRICTS or item["city"] != "臺北市":
            errors.append(f"{item['name']}: invalid city or district")
        if not item["address"] or not item["address_source_url"]:
            errors.append(f"{item['name']}: missing address provenance")
        precision = item["address_precision"]
        if precision not in {"exact", "intersection", "nearby"}:
            errors.append(f"{item['name']}: invalid address_precision")
        if precision == "exact" and (item["district"] not in item["address"] or "號" not in item["address"]):
            errors.append(f"{item['name']}: exact address is incomplete")
        if precision == "intersection" and not any(token in item["address"] for token in ("交叉口", "路口", "巷口")):
            errors.append(f"{item['name']}: intersection address is incomplete")
        if precision == "nearby":
            distance = item["address_distance_m"]
            if not isinstance(distance, (int, float)) or not 0 <= distance <= MAX_NEARBY_METERS:
                errors.append(f"{item['name']}: invalid nearby distance")
        lat, lng = item["latitude"], item["longitude"]
        if (lat is None) != (lng is None):
            errors.append(f"{item['name']}: partial coordinates")
        if lat is not None and not (24.8 <= lat <= 25.3 and 121.3 <= lng <= 121.8):
            errors.append(f"{item['name']}: coordinates outside Taipei area")
    district_rows = district_doc.get("districts", [])
    if len(district_rows) != len(DISTRICTS):
        errors.append("district index must contain all 12 districts")
    collected = []
    for row in district_rows:
        try:
            document = json.loads((api_root / row["path"]).read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{row.get('name')}: cannot load district file: {exc}")
            continue
        if document.get("count") != row.get("count") or document.get("count") != len(document.get("items", [])):
            errors.append(f"{row['name']}: inconsistent district count")
        if any(item.get("district") != row["name"] for item in document.get("items", [])):
            errors.append(f"{row['name']}: district file contains another district")
        collected.extend(document.get("items", []))
    if sorted(collected, key=lambda item: item["id"]) != sorted(items, key=lambda item: item["id"]):
        errors.append("combined district items do not match housing-locations items")
    return errors


def update(args):
    cache = Path(args.cache_dir or os.environ.get("HOUSING_ADDRESS_CACHE", tempfile.gettempdir() + "/housing-address-cache"))
    housing_path = source_path(args.housing_source, cache / "housing-projects.json", refresh=True)
    doorplate_path = source_path(args.doorplate_source, cache / "taipei-doorplates.csv")
    rows = load_source(housing_path)
    projects = select_projects(rows)
    existing_path = API_ROOT / "housing-locations.json"
    if existing_path.exists():
        existing_count = json.loads(existing_path.read_text(encoding="utf-8")).get("count", 0)
        if existing_count and len(projects) < existing_count * MIN_SOURCE_RATIO:
            raise ValueError(f"source guardrail: {len(projects)} projects vs {existing_count} existing")
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    nearest, override_coordinates = match_doorplates(projects, doorplate_path, overrides)
    items = build_items(projects, nearest, override_coordinates, overrides)
    documents = api_documents(items)
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary) / "v1"
        staged = {staging / path.relative_to(API_ROOT): doc for path, doc in documents.items()}
        write_documents(staged)
        errors = validate_api(staging)
        if errors:
            raise ValueError("generated API failed validation:\n" + "\n".join(errors))
    write_documents(documents)
    errors = validate_api()
    if errors:
        raise ValueError("written API failed validation:\n" + "\n".join(errors))
    print(f"housing_locations={len(items)} districts={len(DISTRICTS)} validation=ok")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--housing-source")
    parser.add_argument("--doorplate-source")
    parser.add_argument("--cache-dir")
    args = parser.parse_args()
    try:
        if args.validate_only:
            errors = validate_api()
            if errors:
                print("\n".join(f"ERROR {error}" for error in errors))
                return 1
            count = json.loads((API_ROOT / "housing-locations.json").read_text(encoding="utf-8"))["count"]
            print(f"housing_locations={count} validation=ok")
        else:
            update(args)
        return 0
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
