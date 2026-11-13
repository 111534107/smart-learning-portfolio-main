"""產生目標校系頁用的台灣地圖（SVG 路徑）：讀 g0v/twgeojson 的縣市界，簡化後寫成模板片段。

資料來源：https://github.com/g0v/twgeojson 的 json/twCounty2010.geo.json（CC0 1.0 公眾領域）。
用法（原始檔很大，不放進專案）：
    curl -L -o twCounty2010.geo.json https://raw.githubusercontent.com/g0v/twgeojson/master/json/twCounty2010.geo.json
    python scripts/build_taiwan_map.py twCounty2010.geo.json
會寫出 app/templates/partials/taiwan_map_paths.html。地圖投影與區域劃分在 app/services/school_directory.py，
學校標記的位置用同一個投影算，兩邊一定對得上。金門、連江離本島太遠，地圖上不畫。
"""
import json
import sys

sys.setrecursionlimit(20000)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.school_directory import REGION_OF_COUNTY, normalize_county, project  # noqa: E402

TOLERANCE = 0.006  # 度；約 600 公尺，地圖寬 360 像素時看不出差別
MIN_RING_POINTS = 4
SKIP = {"金門縣", "連江縣"}


def simplify(points, tolerance):
    """Douglas-Peucker 簡化折線。"""
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
    index, distance = 0, -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
        if d > distance:
            index, distance = i, d
    if distance <= tolerance:
        return [points[0], points[-1]]
    return simplify(points[:index + 1], tolerance)[:-1] + simplify(points[index:], tolerance)


def ring_path(ring):
    # 封閉環的頭尾是同一點，直接簡化會全部被刪掉；從中間切成兩半各自簡化再接回來
    middle = len(ring) // 2
    points = simplify(ring[:middle + 1], TOLERANCE)[:-1] + simplify(ring[middle:], TOLERANCE)
    if len(points) < MIN_RING_POINTS:
        return ""
    xy = [project(lon, lat) for lon, lat in points]
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in xy) + "Z"


def main(source):
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    lines = ["{# 自動產生：scripts/build_taiwan_map.py；資料 g0v/twgeojson（CC0）。不要手改。 #}"]
    for feature in data["features"]:
        county = normalize_county(feature["properties"]["COUNTYNAME"])
        if county in SKIP:
            continue
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        d = "".join(ring_path(polygon[0]) for polygon in polygons)
        if d:
            region = REGION_OF_COUNTY[county]
            lines.append(f'<path class="tw-county" data-region="{region}" data-county="{county}" d="{d}"><title>{county}（{region}）</title></path>')
    out = ROOT / "app" / "templates" / "partials" / "taiwan_map_paths.html"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"寫出 {out}（{out.stat().st_size // 1024} KB，{len(lines) - 1} 個縣市）")


if __name__ == "__main__":
    main(sys.argv[1])
