"""
Locust 结果聚合脚本。

读取 tests/perf/results/ 下各档位的 *_stats.csv, 汇总为一张表, 并画性能曲线图。

预期文件名 (由 run_perf.ps1 / run_perf.sh 生成):
    c10_stats.csv, c50_stats.csv, c100_stats.csv, ...
    档位数字从文件名 c<N>_stats.csv 里解析

用法:
    cd BE_smart_lock\smart_lock
    python tests\perf\aggregate_results.py
    python tests\perf\aggregate_results.py --plot  # 需要额外装 matplotlib

产出:
    tests/perf/results/summary_by_endpoint.csv  每接口 x 每档位一行, 报告可直接贴
    tests/perf/results/summary_by_endpoint.md   Markdown 表格 (可直接贴到报告)
    tests/perf/results/perf_curves.png          (可选) 响应时间 & QPS 随并发变化曲线
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CONCURRENCY_RE = re.compile(r"^c(\d+)(?:_[a-z]+)?_stats\.csv$", re.IGNORECASE)


def _discover_csvs() -> List[Tuple[int, Path]]:
    """扫描结果目录, 返回 [(并发数, 文件路径)] 按并发升序。"""
    items: List[Tuple[int, Path]] = []
    if not RESULTS_DIR.is_dir():
        return items
    for path in RESULTS_DIR.glob("c*_stats.csv"):
        m = CONCURRENCY_RE.match(path.name)
        if not m:
            continue
        items.append((int(m.group(1)), path))
    items.sort(key=lambda x: x[0])
    return items


def _read_stats(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fmt(v: str) -> str:
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return v or "-"


# Locust stats.csv 里我们关心的列
COLS = [
    "Name",
    "Request Count",
    "Failure Count",
    "Median Response Time",
    "Average Response Time",
    "95%",
    "99%",
    "Requests/s",
    "Failures/s",
]


def build_summary(csvs: List[Tuple[int, Path]]) -> Dict[str, Dict[int, Dict[str, str]]]:
    """
    返回结构:
        {
          endpoint_name: {
              concurrency: {col: value, ...},
              ...
          },
          ...
        }
    """
    table: Dict[str, Dict[int, Dict[str, str]]] = {}
    for concurrency, path in csvs:
        rows = _read_stats(path)
        for row in rows:
            name = row.get("Name", "").strip()
            if not name:
                continue
            # Locust 会在末尾额外产出一条 Aggregated, 我们保留, 单独展示
            table.setdefault(name, {})[concurrency] = row
    return table


def write_csv(table: Dict[str, Dict[int, Dict[str, str]]], concurrencies: List[int]) -> Path:
    out = RESULTS_DIR / "summary_by_endpoint.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Endpoint", "Concurrency"] + COLS[1:])
        for name, per_c in table.items():
            for c in concurrencies:
                row = per_c.get(c)
                if not row:
                    continue
                writer.writerow([name, c] + [_fmt(row.get(col, "")) for col in COLS[1:]])
    return out


def write_markdown(table: Dict[str, Dict[int, Dict[str, str]]], concurrencies: List[int]) -> Path:
    """输出 Markdown 表格, 每个接口一小节, 报告可直接复制。"""
    out = RESULTS_DIR / "summary_by_endpoint.md"
    lines: List[str] = ["# 接口性能压测汇总", ""]
    lines.append(f"档位: {', '.join(str(c) for c in concurrencies)} 并发")
    lines.append("")
    for name in sorted(table.keys()):
        per_c = table[name]
        lines.append(f"## {name}")
        lines.append("")
        lines.append(
            "| 并发 | 请求数 | 失败数 | 平均(ms) | 中位(ms) | P95(ms) | P99(ms) | QPS |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in concurrencies:
            row = per_c.get(c)
            if not row:
                continue
            lines.append(
                f"| {c} | {_fmt(row.get('Request Count',''))} "
                f"| {_fmt(row.get('Failure Count',''))} "
                f"| {_fmt(row.get('Average Response Time',''))} "
                f"| {_fmt(row.get('Median Response Time',''))} "
                f"| {_fmt(row.get('95%',''))} "
                f"| {_fmt(row.get('99%',''))} "
                f"| {_fmt(row.get('Requests/s',''))} |"
            )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def plot_curves(table: Dict[str, Dict[int, Dict[str, str]]], concurrencies: List[int]) -> Path:
    """画两张子图: P95 响应时间 & QPS 随并发变化。需要 matplotlib。"""
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        print("[aggregate] matplotlib 未安装, 跳过画图。pip install matplotlib 后重试。")
        return Path()

    endpoints = [n for n in table.keys() if n.lower() != "aggregated"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    for name in endpoints:
        xs, p95s, qpss = [], [], []
        for c in concurrencies:
            row = table[name].get(c)
            if not row:
                continue
            try:
                p95 = float(row.get("95%", "") or 0)
                qps = float(row.get("Requests/s", "") or 0)
            except ValueError:
                continue
            xs.append(c)
            p95s.append(p95)
            qpss.append(qps)
        if not xs:
            continue
        ax1.plot(xs, p95s, marker="o", label=name)
        ax2.plot(xs, qpss, marker="s", label=name)

    ax1.set_title("P95 Response Time vs Concurrency")
    ax1.set_xlabel("Concurrency")
    ax1.set_ylabel("P95 (ms)")
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(fontsize=7)

    ax2.set_title("Throughput (QPS) vs Concurrency")
    ax2.set_xlabel("Concurrency")
    ax2.set_ylabel("Requests / s")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(fontsize=7)

    out = RESULTS_DIR / "perf_curves.png"
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plot", action="store_true", help="额外画性能曲线图 (需 matplotlib)")
    args = parser.parse_args()

    csvs = _discover_csvs()
    if not csvs:
        print(f"[aggregate] 在 {RESULTS_DIR} 找不到 c*_stats.csv, 先跑 run_perf 生成数据。")
        return

    concurrencies = [c for c, _ in csvs]
    print(f"[aggregate] 发现档位: {concurrencies}")
    table = build_summary(csvs)

    csv_path = write_csv(table, concurrencies)
    md_path = write_markdown(table, concurrencies)
    print(f"[aggregate] CSV:      {csv_path}")
    print(f"[aggregate] Markdown: {md_path}")

    if args.plot:
        png_path = plot_curves(table, concurrencies)
        if png_path:
            print(f"[aggregate] 曲线图: {png_path}")

    agg = table.get("Aggregated")
    if agg:
        print("\n==== Aggregated 汇总 ====")
        print(f"{'并发':<6}{'QPS':>10}{'平均ms':>10}{'P95ms':>10}{'失败':>8}")
        for c in concurrencies:
            row = agg.get(c)
            if not row:
                continue
            print(
                f"{c:<6}"
                f"{_fmt(row.get('Requests/s','')):>10}"
                f"{_fmt(row.get('Average Response Time','')):>10}"
                f"{_fmt(row.get('95%','')):>10}"
                f"{_fmt(row.get('Failure Count','')):>8}"
            )


if __name__ == "__main__":
    main()
