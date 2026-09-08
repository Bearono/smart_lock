"""
端到端时延测量脚本。

目的:
    测量单次开门请求的完整链路耗时, 拆分为各阶段, 用于在报告里画阶段耗时堆叠图。

链路拆分 (前端视角):
    T0  发起 /api/login                            -> 登录耗时 (含 bcrypt)
    T1  发起 /api/mfa/open-door/request            -> 会话创建 + 设备派发
    T2  发起 /api/mfa/open-door/face-result (模拟)  -> 人脸结果回传
    T3  发起 /api/mfa/open-door/confirm            -> 汇总因子, 签发 unlock_token
    T4  发起 /api/lock/unlock-token/verify         -> 硬件消费令牌, 门锁翻转

注意:
    - 默认使用 perf_user_001 (需事先通过 prepare_data.py 建好并绑设备)
    - 为避免走真实树莓派, 请把后端环境变量 DEVICE_DISPATCH_REQUIRED=false
      这样 /open-door/request 会走开发兜底, 直接把 face_verified 置为 True
    - 该脚本适合跑 20~50 次取均值/标准差, 而不是并发压测
    - 如果处于深夜 (22:00-06:00), 后端会要求 TOTP, 本脚本不覆盖, 请在白天跑

使用:
    cd BE_smart_lock\smart_lock
    .\.venv\Scripts\Activate.ps1
    python tests\perf\measure_e2e.py                  # 默认 20 次
    python tests\perf\measure_e2e.py --runs 50 --host http://localhost:8000

产出:
    tests\perf\results\e2e_stages.csv     每次运行各阶段耗时明细 (ms)
    tests\perf\results\e2e_summary.csv    均值/中位数/P95/标准差
    控制台会直接打印摘要表
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests


DEFAULT_HOST = os.environ.get("PERF_HOST", "http://localhost:8000")
DEFAULT_USER = os.environ.get("PERF_E2E_USER", "perf_user_001")
DEFAULT_PASSWORD = os.environ.get("PERF_USER_PASSWORD", "Perf@123456")
DEFAULT_DEVICE = os.environ.get("PERF_DEVICE_ID", "door_01")

STAGES = ["login", "open_request", "face_result", "confirm", "token_verify"]


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _stage(elapsed_start: float) -> float:
    return _now_ms() - elapsed_start


def _login(session: requests.Session, host: str, username: str, password: str) -> Optional[str]:
    resp = session.post(
        f"{host}/api/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"[e2e] login failed: {resp.status_code} {resp.text[:120]}")
        return None
    return resp.json().get("access_token")


def _one_run(
    session: requests.Session,
    host: str,
    username: str,
    password: str,
    device_id: str,
) -> Optional[Dict[str, float]]:
    stages: Dict[str, float] = {}

    # T0 login
    t = _now_ms()
    token = _login(session, host, username, password)
    if not token:
        return None
    stages["login"] = _stage(t)
    headers = {"Authorization": f"Bearer {token}"}

    # T1 open-door/request
    t = _now_ms()
    r1 = session.post(
        f"{host}/api/mfa/open-door/request",
        json={"device_id": device_id},
        headers=headers,
        timeout=15,
    )
    stages["open_request"] = _stage(t)
    if r1.status_code != 200:
        print(f"[e2e] open request failed: {r1.status_code} {r1.text[:120]}")
        return None
    request_id = r1.json().get("request_id")
    nonce = r1.json().get("nonce")
    requires_totp = r1.json().get("requires_totp", False)
    if requires_totp:
        print("[e2e] 当前时间段需要 TOTP, 跳过本次运行 (请白天跑或关闭深夜策略)")
        return None

    # T2 face-result (模拟树莓派回传, 免鉴权)
    t = _now_ms()
    r2 = session.post(
        f"{host}/api/mfa/open-door/face-result",
        json={
            "request_id": request_id,
            "device_id": device_id,
            "face_user_id": username,
            "similarity_score": 0.92,
            "nonce": nonce,
        },
        timeout=15,
    )
    stages["face_result"] = _stage(t)
    # 若 request 已在设备派发兜底里把 face_verified 置 True, 这里可能返回 400 already processed,
    # 视为已完成, 不算失败。
    if r2.status_code not in (200, 400):
        print(f"[e2e] face-result unexpected: {r2.status_code} {r2.text[:120]}")

    # T3 open-door/confirm
    t = _now_ms()
    r3 = session.post(
        f"{host}/api/mfa/open-door/confirm",
        json={"request_id": request_id},
        headers=headers,
        timeout=15,
    )
    stages["confirm"] = _stage(t)
    if r3.status_code != 200:
        print(f"[e2e] confirm failed: {r3.status_code} {r3.text[:120]}")
        return None
    unlock_token = r3.json().get("unlock_token")
    if not unlock_token:
        return None

    # T4 unlock-token/verify (硬件消费, 免鉴权)
    t = _now_ms()
    r4 = session.post(
        f"{host}/api/lock/unlock-token/verify",
        json={"device_id": device_id, "unlock_token": unlock_token},
        timeout=15,
    )
    stages["token_verify"] = _stage(t)
    if r4.status_code != 200:
        print(f"[e2e] token verify failed: {r4.status_code} {r4.text[:120]}")

    stages["total"] = sum(stages[s] for s in STAGES)
    return stages


def _summarize(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0, "median": 0, "p95": 0, "min": 0, "max": 0, "stdev": 0}
    values_sorted = sorted(values)
    p95_idx = max(0, min(len(values_sorted) - 1, int(round(0.95 * (len(values_sorted) - 1)))))
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "p95": values_sorted[p95_idx],
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=2, help="预热次数, 结果不计入统计")
    args = parser.parse_args()

    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[e2e] host={args.host} user={args.user} device={args.device} "
        f"warmup={args.warmup} runs={args.runs}"
    )

    with requests.Session() as session:
        for i in range(args.warmup):
            _one_run(session, args.host, args.user, args.password, args.device)
            print(f"  warmup {i + 1}/{args.warmup}")

        runs: List[Dict[str, float]] = []
        for i in range(args.runs):
            r = _one_run(session, args.host, args.user, args.password, args.device)
            if r is None:
                print(f"  run {i + 1}/{args.runs}: SKIPPED")
                continue
            runs.append(r)
            print(
                f"  run {i + 1}/{args.runs}: total={r['total']:.1f}ms  "
                f"login={r['login']:.1f}  open={r['open_request']:.1f}  "
                f"face={r['face_result']:.1f}  confirm={r['confirm']:.1f}  "
                f"verify={r['token_verify']:.1f}"
            )

    if not runs:
        print("[e2e] 没有有效样本, 请检查后端状态和测试账号")
        sys.exit(1)

    # 明细 CSV
    detail_path = results_dir / "e2e_stages.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["run"] + STAGES + ["total"])
        for i, r in enumerate(runs, 1):
            writer.writerow([i] + [f"{r[s]:.3f}" for s in STAGES] + [f"{r['total']:.3f}"])

    # 汇总 CSV
    summary_path = results_dir / "e2e_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["stage", "n", "mean_ms", "median_ms", "p95_ms", "min_ms", "max_ms", "stdev_ms"])
        for stage in STAGES + ["total"]:
            values = [r[stage] for r in runs]
            summary = _summarize(values)
            writer.writerow([
                stage,
                summary["n"],
                f"{summary['mean']:.2f}",
                f"{summary['median']:.2f}",
                f"{summary['p95']:.2f}",
                f"{summary['min']:.2f}",
                f"{summary['max']:.2f}",
                f"{summary['stdev']:.2f}",
            ])

    print("\n==== 端到端时延摘要 (ms) ====")
    print(f"{'stage':<15}{'mean':>10}{'median':>10}{'p95':>10}{'stdev':>10}")
    for stage in STAGES + ["total"]:
        values = [r[stage] for r in runs]
        s = _summarize(values)
        print(f"{stage:<15}{s['mean']:>10.2f}{s['median']:>10.2f}{s['p95']:>10.2f}{s['stdev']:>10.2f}")
    print(f"\n明细: {detail_path}")
    print(f"摘要: {summary_path}")


if __name__ == "__main__":
    main()
