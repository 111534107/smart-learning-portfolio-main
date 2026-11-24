"""把 verify_all.ps1 的各項結果整理成一份 summary.md（給 Claude 與人快速讀）。

用法：python -X utf8 scripts/verify_summary.py <輸出資料夾>
讀取：layout\\report.json（畫面檢查）、pytest.txt（完整測試輸出）、server_ok.txt（測試站是否啟動）。
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path


def layout_section(out: Path) -> list[str]:
    report = out / "layout" / "report.json"
    if not report.exists():
        return ["## 畫面檢查", "", "沒有產生報告（沒有執行，或執行中斷）。", ""]
    data = json.loads(report.read_text(encoding="utf-8"))
    failed = [r for r in data if r["failures"]]
    lines = ["## 畫面檢查", "", f"- 通過 {len(data) - len(failed)}／{len(data)}，未過 {len(failed)}", ""]
    if failed:
        kinds = Counter()
        for row in failed:
            for text in row["failures"]:
                kinds[text.split("：")[0]] += 1
        lines += ["### 未過原因統計（同一類先一起修）", ""]
        lines += [f"- {kind}：{count} 組" for kind, count in kinds.most_common()]
        lines += ["", "### 未過清單", "", "| 頁面 | 尺寸 | 主題 | 第一項原因 |", "| --- | --- | --- | --- |"]
        for row in failed:
            reason = row["failures"][0].replace("\n", " ").replace("|", "／")[:70]
            lines.append(f"| {row['page']} | {row['size']} | {row['theme']} | {reason} |")
        lines.append("")
    return lines


def test_section(out: Path) -> list[str]:
    text_file = out / "pytest.txt"
    if not text_file.exists():
        return ["## 完整測試", "", "沒有執行。", ""]
    text = text_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    last = text[-1] if text else "（沒有輸出）"
    failed = [line for line in text if line.startswith("FAILED")]
    lines = ["## 完整測試", "", f"- 結果列：`{last}`"]
    if failed:
        lines += ["", "### 失敗的測試", ""] + [f"- {line}" for line in failed[:30]]
    return lines + [""]


def main() -> int:
    out = Path(sys.argv[1])
    server = (out / "server_ok.txt").read_text(encoding="utf-8-sig").strip() if (out / "server_ok.txt").exists() else "未知"
    lines = ["# 驗證摘要", "", f"- 測試站：{server}", ""]
    lines += layout_section(out) + test_section(out)
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"\n完整摘要：{out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
