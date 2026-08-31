#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build and validate the nationwide social-housing static API (v2)."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote


REPO = Path(__file__).resolve().parents[4]
API_ROOT = REPO / "api/v2"
OVERRIDES = REPO / ".claude/skills/housing-doc-to-json/batch/nationwide_address_overrides.json"
V1_API = REPO / "api/v1/housing-locations.json"

MOI_URL = "https://pip.moi.gov.tw/V3/B/SCRB0505.aspx"
MOI_INDEX_URL = "https://pip.moi.gov.tw/V3/B/SCRB0507.aspx"
NHURC_API_ROOT = "https://www.socialhousing.tw/Portalsvc/api"
NHURC_PORTAL = "https://www.socialhousing.tw/portal"
MAX_NEARBY_METERS = 250.0
MIN_SOURCE_RATIO = 0.90

REGIONS = {
    "臺北市": "taipei-city", "新北市": "new-taipei-city",
    "桃園市": "taoyuan-city", "臺中市": "taichung-city",
    "臺南市": "tainan-city", "高雄市": "kaohsiung-city",
    "基隆市": "keelung-city", "新竹市": "hsinchu-city",
    "嘉義市": "chiayi-city", "新竹縣": "hsinchu-county",
    "苗栗縣": "miaoli-county", "彰化縣": "changhua-county",
    "南投縣": "nantou-county", "雲林縣": "yunlin-county",
    "嘉義縣": "chiayi-county", "屏東縣": "pingtung-county",
    "宜蘭縣": "yilan-county", "花蓮縣": "hualien-county",
    "臺東縣": "taitung-county", "澎湖縣": "penghu-county",
    "金門縣": "kinmen-county", "連江縣": "lienchiang-county",
}

STATUS_MAP = {
    "既有": "已完工", "新完工": "已完工", "已完工": "已完工",
    "興建中": "施工中", "施工中": "施工中",
    "已決標待開工": "待開工", "已決標": "待開工", "待開工": "待開工",
    "規劃中": "規劃中",
}
VALID_STATUSES = set(STATUS_MAP.values())
VALID_PRECISIONS = {"exact", "intersection", "nearby"}
EXCLUDE_PATTERNS = (
    re.compile(r"國產署包租案件"), re.compile(r"包租代管"),
    re.compile(r"合計|總計|共\d+處"),
)
REQUIRED_KEY_ORDER = (
    "id", "name", "county", "district", "address", "address_precision",
    "address_method", "address_distance_m", "official_location", "latitude",
    "longitude", "households", "residents", "floors", "status",
    "official_status", "project_type", "organizer", "source_urls", "updated_at",
)
REQUIRED_KEYS = set(REQUIRED_KEY_ORDER)


def normalize_text(value):
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("台灣", "臺灣").replace("台北", "臺北").replace("台中", "臺中")
    text = text.replace("台南", "臺南").replace("台東", "臺東")
    return re.sub(r"\s+", "", text).strip()


def normalize_name(value):
    text = normalize_text(value).upper()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s()（）·・,，、/／\-—_]|新建工程|社會住宅|社宅", "", text)


def nullable_int(value):
    text = normalize_text(value).replace(",", "")
    return int(text) if re.fullmatch(r"\d+", text) else None


def nullable_float(value):
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result else None


def stable_id(county, name, organizer):
    key = "\0".join(normalize_text(x) for x in (county, name, organizer)).encode("utf-8")
    return "tw-" + hashlib.sha256(key).hexdigest()[:16]


def district_code(county, district):
    key = f"{normalize_text(county)}\0{normalize_text(district)}".encode("utf-8")
    return "d-" + hashlib.sha256(key).hexdigest()[:10]


def canonical_county(value):
    value = normalize_text(value)
    aliases = {"台北市": "臺北市", "台中市": "臺中市", "台南市": "臺南市", "台東縣": "臺東縣"}
    return aliases.get(value, value)


def canonical_address(value, county, district):
    address = normalize_text(value)
    if not address:
        return ""
    if not address.startswith(county):
        if address.startswith(district):
            address = county + address
        elif district not in address[:12]:
            address = county + district + address
        else:
            address = county + address
    return address


def infer_district(name, county):
    text = normalize_text(name).removeprefix(county)
    match = re.search(r"([\u4e00-\u9fff]{1,5}(?:區|鄉|鎮|市))", text)
    return match.group(1) if match else ""


def project_type(organizer):
    organizer = normalize_text(organizer)
    if "中央" in organizer or "住都中心" in organizer:
        return "中央興辦"
    if organizer:
        return "地方興辦"
    return "其他"


class MoiTableParser(HTMLParser):
    """Read data rows from the status tables on SCRB0505."""

    TABLES = {"t1", "t2", "t3", "t4", "t5"}

    def __init__(self):
        super().__init__()
        self.table = None
        self.row = None
        self.cell = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("id") in self.TABLES:
            self.table = attrs["id"]
        elif self.table and tag == "tr":
            self.row = []
        elif self.row is not None and tag == "td":
            self.cell = []
        elif self.cell is not None and tag == "br":
            self.cell.append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if len(self.row) == 8:
                self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            self.table = None


def curl_download(url, destination, referer=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    command = [
        "curl", "--fail", "--location", "--compressed", "--silent", "--show-error",
        "--retry", "3", "--retry-delay", "2",
        "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    ]
    if referer:
        command.extend(["--referer", referer])
    command.extend(["--output", str(temporary), url])
    try:
        subprocess.run(command, check=True)
        if temporary.stat().st_size < 100:
            raise ValueError(f"download is unexpectedly small: {url}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def parse_moi_html(text):
    parser = MoiTableParser()
    parser.feed(text)
    result = []
    for cells in parser.rows:
        county, name, organizer, households, awarded, started, completed, official_status = cells
        official_status = normalize_text(official_status)
        excluded_reason = next((p.pattern for p in EXCLUDE_PATTERNS if p.search(name)), None)
        row = {
            "county": canonical_county(county), "name": normalize_text(name),
            "organizer": normalize_text(organizer), "households": nullable_int(households),
            "award_date": normalize_text(awarded) or None,
            "start_date": normalize_text(started) or None,
            "completion_date": normalize_text(completed) or None,
            "official_status": official_status,
            "status": STATUS_MAP.get(official_status), "excluded_reason": excluded_reason,
        }
        result.append(row)
    return result


def load_moi(cache, source_dir=None, refresh=True):
    rows = []
    source_dir = Path(source_dir) if source_dir else None
    for county in REGIONS:
        path = (source_dir / f"{REGIONS[county]}.html") if source_dir else (cache / "moi" / f"{REGIONS[county]}.html")
        if not source_dir and (refresh or not path.exists()):
            curl_download(f"{MOI_URL}?city={quote(county)}", path, MOI_INDEX_URL)
        source = path.read_text(encoding="utf-8")
        parsed = parse_moi_html(source)
        if not parsed:
            title = re.search(r"<title[^>]*>(.*?)</title>", source, re.IGNORECASE | re.DOTALL)
            table_ids = sorted(set(re.findall(r'<table[^>]+id=["\']?([^"\' >]+)', source, re.IGNORECASE)))
            title_text = re.sub(r"\s+", " ", title.group(1)).strip()[:100] if title else ""
            raise ValueError(
                f"{county}: MOI source contains no cases "
                f"(bytes={len(source.encode('utf-8'))}, title={title_text!r}, table_ids={table_ids})"
            )
        if any(row["county"] != county for row in parsed):
            raise ValueError(f"{county}: MOI source returned another county")
        rows.extend(parsed)
    return rows


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def nhurc_request(url, destination):
    return curl_download(url, destination, NHURC_PORTAL)


def load_nhurc(cache, list_source=None, detail_dir=None, refresh=True):
    list_path = Path(list_source) if list_source else cache / "nhurc" / "normal-list.json"
    if not list_source and (refresh or not list_path.exists()):
        nhurc_request(f"{NHURC_API_ROOT}/Building/Normal/List", list_path)
    payload = load_json(list_path)
    rows = payload.get("Data", payload if isinstance(payload, list) else [])
    unique = {}
    for row in rows:
        county = canonical_county(row.get("NM_CITY"))
        number = normalize_text(row.get("NO_BUILD"))
        if county in REGIONS and number:
            unique[(county, number)] = row
    details = {}
    detail_root = Path(detail_dir) if detail_dir else cache / "nhurc" / "details"
    for (county, number), summary in unique.items():
        path = detail_root / f"{county}-{number}.json"
        if not detail_dir and (refresh or not path.exists()):
            nhurc_request(f"{NHURC_API_ROOT}/Building/Normal/{number}/Detail", path)
        payload = load_json(path)
        detail = payload.get("Data", payload)
        details[(county, normalize_name(summary.get("NM_BUILD")))] = {
            "county": county,
            "district": normalize_text(summary.get("NM_TOWN")),
            "name": normalize_text(summary.get("NM_BUILD")),
            "address": normalize_text(detail.get("GN_ADDR")),
            "floors": normalize_text(detail.get("GN_BUILD_SCALE")) or None,
            "households": nullable_int(detail.get("QT_HOUSE")),
            "map": detail.get("GOOGLE_MAP"),
            "source_url": f"https://www.socialhousing.tw/Portal/BuildDetail?BuildingNo={number}&BuildingType=Normal",
        }
    return details


def coordinates_from_map(value):
    if not value:
        return None, None
    match = re.search(r"!2d(1[12]\d(?:\.\d+)?)!3d(2\d(?:\.\d+)?)", value)
    return (float(match.group(2)), float(match.group(1))) if match else (None, None)


def load_v1():
    if not V1_API.exists():
        return {}
    rows = load_json(V1_API).get("items", [])
    return {("臺北市", normalize_name(row["name"])): row for row in rows}


def override_key(row):
    return f'{row["county"]}/{row["name"]}/{row["organizer"]}'


def load_overrides(path=OVERRIDES):
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError("nationwide overrides must be an object")
    return data


def resolve_project(row, overrides, nhurc, v1):
    key = override_key(row)
    alias = overrides.get("aliases", {}).get(key)
    lookup_name = normalize_name(alias or row["name"])
    manual = overrides.get("projects", {}).get(key)
    source_urls = [f"{MOI_URL}?city={quote(row['county'])}"]
    address = district = precision = method = ""
    distance = latitude = longitude = floors = residents = None
    official_location = row["name"] if "地號" in row["name"] or "基地" in row["name"] else None

    if manual:
        district = normalize_text(manual.get("district"))
        address = canonical_address(manual.get("address"), row["county"], district)
        precision = normalize_text(manual.get("address_precision"))
        method = normalize_text(manual.get("address_method")) or "curated_official"
        distance = nullable_float(manual.get("address_distance_m"))
        latitude = nullable_float(manual.get("latitude"))
        longitude = nullable_float(manual.get("longitude"))
        floors = normalize_text(manual.get("floors")) or None
        residents = nullable_int(manual.get("residents"))
        official_location = normalize_text(manual.get("official_location")) or official_location
        source_urls.extend(manual.get("source_urls", []))
    elif (row["county"], lookup_name) in nhurc:
        detail = nhurc[(row["county"], lookup_name)]
        district = detail["district"]
        address = canonical_address(detail["address"], row["county"], district)
        precision, method, distance = "exact", "official_address", None
        latitude, longitude = coordinates_from_map(detail["map"])
        floors = detail["floors"]
        source_urls.append(detail["source_url"])
    elif (row["county"], lookup_name) in v1:
        detail = v1[(row["county"], lookup_name)]
        district = detail["district"]
        address = detail["address"]
        precision = detail["address_precision"]
        method = "taipei_v1_" + detail["address_method"]
        distance = detail["address_distance_m"]
        latitude, longitude = detail["latitude"], detail["longitude"]
        floors, residents = detail["floors"], detail["residents"]
        official_location = detail["official_location"] or official_location
        source_urls.append(detail["address_source_url"])
    else:
        district = infer_district(row["name"], row["county"])

    if not address or not district:
        return None, {
            "key": key, "county": row["county"], "name": row["name"],
            "organizer": row["organizer"], "inferred_district": district or None,
            "reason": "missing verified navigable address" if not address else "missing district",
        }
    item = {
        "id": stable_id(row["county"], row["name"], row["organizer"]),
        "name": row["name"], "county": row["county"], "district": district,
        "address": address, "address_precision": precision,
        "address_method": method, "address_distance_m": distance,
        "official_location": official_location,
        "latitude": round(latitude, 6) if latitude is not None else None,
        "longitude": round(longitude, 6) if longitude is not None else None,
        "households": row["households"], "residents": residents, "floors": floors,
        "status": row["status"], "official_status": row["official_status"],
        "project_type": project_type(row["organizer"]), "organizer": row["organizer"],
        "source_urls": list(dict.fromkeys(url for url in source_urls if url)),
        "updated_at": None,
    }
    return item, None


def extra_items(overrides):
    items = []
    for raw in overrides.get("extra_projects", []):
        row = dict(raw)
        row["county"] = canonical_county(row.get("county"))
        row["name"] = normalize_text(row.get("name"))
        row["organizer"] = normalize_text(row.get("organizer"))
        row["status"] = STATUS_MAP.get(normalize_text(row.get("status")), normalize_text(row.get("status")))
        row["official_status"] = normalize_text(row.get("official_status")) or row["status"]
        row.setdefault("project_type", project_type(row["organizer"]))
        row.setdefault("address_distance_m", None)
        row.setdefault("official_location", None)
        row.setdefault("latitude", None)
        row.setdefault("longitude", None)
        row.setdefault("households", None)
        row.setdefault("residents", None)
        row.setdefault("floors", None)
        row.setdefault("source_urls", [])
        row["id"] = stable_id(row["county"], row["name"], row["organizer"])
        row["updated_at"] = None
        items.append({key: row.get(key) for key in REQUIRED_KEY_ORDER})
    return items


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def existing_timestamp(items):
    path = API_ROOT / "housing-locations.json"
    comparable = [{**item, "updated_at": None} for item in items]
    if path.exists():
        try:
            existing = load_json(path)
            previous = [{**item, "updated_at": None} for item in existing.get("items", [])]
            if previous == comparable:
                return existing.get("updated_at")
        except Exception:
            pass
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def api_documents(items, source_stats):
    region_root = API_ROOT / "regions"
    district_root = API_ROOT / "districts"
    updated_at = existing_timestamp(items)
    for item in items:
        item["updated_at"] = updated_at
    source = {
        "moi_cases_url": MOI_URL, "moi_index_url": MOI_INDEX_URL,
        "nhurc_portal_url": NHURC_PORTAL,
    }
    common = {"schema_version": "2.0", "updated_at": updated_at, "source": source}
    documents = {API_ROOT / "housing-locations.json": {**common, "count": len(items), "items": items}}
    region_rows = []
    district_rows = []
    for county, code in REGIONS.items():
        region_items = [item for item in items if item["county"] == county]
        status_counts = dict(sorted(Counter(item["status"] for item in region_items).items()))
        districts = sorted({item["district"] for item in region_items})
        region_path = f"regions/{code}.json"
        region_rows.append({
            "code": code, "name": county, "count": len(region_items),
            "district_count": len(districts), "status_counts": status_counts,
            "path": region_path,
        })
        documents[region_root / f"{code}.json"] = {
            **common, "region": county, "region_code": code,
            "count": len(region_items), "status_counts": status_counts, "items": region_items,
        }
        for district in districts:
            code2 = district_code(county, district)
            district_items = [item for item in region_items if item["district"] == district]
            path = f"districts/{code}/{code2}.json"
            district_rows.append({
                "region_code": code, "region": county, "code": code2,
                "name": district, "count": len(district_items), "path": path,
            })
            documents[district_root / code / f"{code2}.json"] = {
                **common, "region": county, "region_code": code,
                "district": district, "district_code": code2,
                "count": len(district_items), "items": district_items,
            }
    documents[API_ROOT / "regions.json"] = {**common, "count": len(region_rows), "regions": region_rows}
    documents[API_ROOT / "districts.json"] = {**common, "count": len(district_rows), "districts": district_rows}
    documents[API_ROOT / "index.json"] = {
        **common, "housing_count": len(items), "region_count": len(region_rows),
        "district_count": len(district_rows), "source_stats": source_stats,
        "endpoints": {
            "all": "housing-locations.json", "regions": "regions.json",
            "region": "regions/{region-code}.json", "districts": "districts.json",
            "district": "districts/{region-code}/{district-code}.json",
        },
    }
    return documents


def validate_api(api_root=API_ROOT):
    errors = []
    try:
        all_doc = load_json(api_root / "housing-locations.json")
        regions_doc = load_json(api_root / "regions.json")
        districts_doc = load_json(api_root / "districts.json")
        index_doc = load_json(api_root / "index.json")
    except Exception as exc:
        return [f"API files cannot be loaded: {exc}"]
    items = all_doc.get("items", [])
    if all_doc.get("count") != len(items) or index_doc.get("housing_count") != len(items):
        errors.append("housing count is inconsistent")
    ids = set()
    names = set()
    for item in items:
        missing = REQUIRED_KEYS - set(item)
        if missing:
            errors.append(f"{item.get('name', '<unknown>')}: missing {sorted(missing)}")
            continue
        if item["id"] in ids:
            errors.append(f"{item['name']}: duplicate id")
        name_key = (item["county"], item["district"], item["name"])
        if name_key in names:
            errors.append(f"{item['name']}: duplicate county/district/name")
        ids.add(item["id"])
        names.add(name_key)
        if item["county"] not in REGIONS or not item["district"]:
            errors.append(f"{item['name']}: invalid county or district")
        if item["status"] not in VALID_STATUSES:
            errors.append(f"{item['name']}: invalid status")
        if not item["address"] or not item["address_method"] or not item["source_urls"]:
            errors.append(f"{item['name']}: missing address provenance")
        precision = item["address_precision"]
        if precision not in VALID_PRECISIONS:
            errors.append(f"{item['name']}: invalid address_precision")
        if precision == "exact" and not (
            item["county"] in item["address"] and item["district"] in item["address"] and "號" in item["address"]
        ):
            errors.append(f"{item['name']}: exact address is incomplete")
        if precision == "intersection" and not (
            item["district"] in item["address"]
            and any(token in item["address"] for token in ("交叉口", "路口", "巷口"))
            and any(token in item["address"] for token in ("與", "及", "、"))
        ):
            errors.append(f"{item['name']}: intersection address is incomplete")
        if precision == "nearby":
            distance = item["address_distance_m"]
            if not isinstance(distance, (int, float)) or not 0 <= distance <= MAX_NEARBY_METERS:
                errors.append(f"{item['name']}: invalid nearby distance")
        lat, lng = item["latitude"], item["longitude"]
        if (lat is None) != (lng is None):
            errors.append(f"{item['name']}: partial coordinates")
        if lat is not None and not (20.0 <= lat <= 27.0 and 118.0 <= lng <= 123.0):
            errors.append(f"{item['name']}: coordinates outside Taiwan")
    region_rows = regions_doc.get("regions", [])
    if len(region_rows) != len(REGIONS) or {row.get("name") for row in region_rows} != set(REGIONS):
        errors.append("region index must contain all 22 regions")
    collected = []
    for row in region_rows:
        path = api_root / row.get("path", "")
        try:
            document = load_json(path)
        except Exception as exc:
            errors.append(f"{row.get('name')}: cannot load region file: {exc}")
            continue
        region_items = document.get("items", [])
        if row.get("count") != len(region_items) or document.get("count") != len(region_items):
            errors.append(f"{row.get('name')}: inconsistent region count")
        if any(item.get("county") != row.get("name") for item in region_items):
            errors.append(f"{row.get('name')}: region file contains another county")
        collected.extend(region_items)
    if sorted(collected, key=lambda x: x["id"]) != sorted(items, key=lambda x: x["id"]):
        errors.append("combined region items do not match all items")
    district_collected = []
    for row in districts_doc.get("districts", []):
        try:
            document = load_json(api_root / row["path"])
        except Exception as exc:
            errors.append(f"{row.get('name')}: cannot load district file: {exc}")
            continue
        district_items = document.get("items", [])
        if row.get("count") != len(district_items) or document.get("count") != len(district_items):
            errors.append(f"{row.get('region')}/{row.get('name')}: inconsistent district count")
        if any(item.get("county") != row.get("region") or item.get("district") != row.get("name") for item in district_items):
            errors.append(f"{row.get('region')}/{row.get('name')}: district file contains another area")
        district_collected.extend(district_items)
    if sorted(district_collected, key=lambda x: x["id"]) != sorted(items, key=lambda x: x["id"]):
        errors.append("combined district items do not match all items")
    return errors


def write_documents(documents):
    expected = set(documents)
    if API_ROOT.exists():
        for path in API_ROOT.rglob("*.json"):
            if path not in expected:
                path.unlink()
    for path, document in documents.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json_text(document)
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")


def compare_existing(items):
    path = API_ROOT / "housing-locations.json"
    previous = {}
    if path.exists():
        previous = {item["id"]: item for item in load_json(path).get("items", [])}
    current = {item["id"]: item for item in items}
    added = sorted(current.keys() - previous.keys())
    removed = sorted(previous.keys() - current.keys())
    changed = []
    for identifier in current.keys() & previous.keys():
        before = {**previous[identifier], "updated_at": None}
        after = {**current[identifier], "updated_at": None}
        if before != after:
            changed.append(identifier)
    return {"added": len(added), "changed": len(changed), "removed": len(removed)}


def summary_text(source_stats, change_stats, items, unresolved):
    lines = [
        "## 全臺社宅位置 API v2", "",
        f"- 內政部原始個案：{source_stats['discovered']}",
        f"- 排除批次／彙總列：{source_stats['excluded']}",
        f"- 已取得明確地址：{len(items)}", f"- 待人工補地址：{len(unresolved)}",
        f"- 相較既有 v2：新增 {change_stats['added']}、異動 {change_stats['changed']}、移除 {change_stats['removed']}",
        "",
    ]
    for county in REGIONS:
        count = sum(item["county"] == county for item in items)
        pending = sum(row["county"] == county for row in unresolved)
        lines.append(f"- {county}：{count} 筆；待處理 {pending} 筆")
    return "\n".join(lines) + "\n"


def update(args):
    cache = Path(args.cache_dir or os.environ.get("HOUSING_NATIONWIDE_CACHE", tempfile.gettempdir() + "/housing-nationwide-cache"))
    overrides = load_overrides(Path(args.overrides) if args.overrides else OVERRIDES)
    moi_rows = load_moi(cache, args.moi_source_dir, refresh=not args.no_refresh)
    excluded = [row for row in moi_rows if row["excluded_reason"]]
    selected = [row for row in moi_rows if not row["excluded_reason"]]
    invalid_status = [row for row in selected if row["status"] not in VALID_STATUSES]
    if invalid_status:
        raise ValueError("unknown MOI status: " + ", ".join(sorted({row["official_status"] for row in invalid_status})))
    nhurc = load_nhurc(cache, args.nhurc_list, args.nhurc_detail_dir, refresh=not args.no_refresh)
    v1 = load_v1()
    items, unresolved = [], []
    for row in selected:
        item, problem = resolve_project(row, overrides, nhurc, v1)
        if item:
            items.append(item)
        else:
            unresolved.append(problem)
    items.extend(extra_items(overrides))
    items.sort(key=lambda x: (REGIONS[x["county"]], x["district"], x["name"], x["organizer"]))
    source_stats = {"discovered": len(moi_rows), "excluded": len(excluded), "selected": len(selected)}
    change_stats = compare_existing(items)
    existing_count = 0
    if (API_ROOT / "housing-locations.json").exists():
        existing_count = load_json(API_ROOT / "housing-locations.json").get("count", 0)
    if existing_count and len(items) < existing_count * MIN_SOURCE_RATIO:
        raise ValueError(f"source guardrail: {len(items)} resolved projects vs {existing_count} existing")
    summary = summary_text(source_stats, change_stats, items, unresolved)
    if args.summary or os.environ.get("HOUSING_UPDATE_SUMMARY"):
        path = Path(args.summary or os.environ["HOUSING_UPDATE_SUMMARY"])
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(existing + ("\n" if existing else "") + summary, encoding="utf-8")
    unresolved_path = cache / "unresolved-projects.json"
    unresolved_path.parent.mkdir(parents=True, exist_ok=True)
    unresolved_path.write_text(json_text({"count": len(unresolved), "items": unresolved}), encoding="utf-8")
    if unresolved:
        if args.audit_only:
            print(
                f"nationwide_discovered={len(moi_rows)} selected={len(selected)} "
                f"resolved={len(items)} unresolved={len(unresolved)} audit=ok"
            )
            return
        raise ValueError(f"{len(unresolved)} projects have no verified navigable address; review {unresolved_path}")
    if len(items) != len(selected) + len(overrides.get("extra_projects", [])):
        raise ValueError("source reconciliation failed")
    documents = api_documents(items, source_stats)
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary) / "v2"
        staged = {staging / path.relative_to(API_ROOT): document for path, document in documents.items()}
        for path, document in staged.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json_text(document), encoding="utf-8")
        errors = validate_api(staging)
        if errors:
            raise ValueError("generated API failed validation:\n" + "\n".join(errors))
    write_documents(documents)
    errors = validate_api()
    if errors:
        raise ValueError("written API failed validation:\n" + "\n".join(errors))
    print(f"nationwide_housing={len(items)} regions={len(REGIONS)} validation=ok")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--cache-dir")
    parser.add_argument("--moi-source-dir")
    parser.add_argument("--nhurc-list")
    parser.add_argument("--nhurc-detail-dir")
    parser.add_argument("--overrides")
    parser.add_argument("--summary")
    parser.add_argument("--no-refresh", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.validate_only:
            errors = validate_api()
            if errors:
                print("\n".join(f"ERROR {error}" for error in errors))
                return 1
            count = load_json(API_ROOT / "housing-locations.json")["count"]
            print(f"nationwide_housing={count} validation=ok")
        else:
            update(args)
        return 0
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
