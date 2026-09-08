"""
Locust 性能测试脚本 —— 智能锁后端接口负载压测。

覆盖接口:
    - POST /api/login                  登录 (含 bcrypt, 通常最慢, 单独一档)
    - GET  /api/lock/status            查询门锁状态
    - POST /api/lock/control           控制门锁 (LOCK/UNLOCK 循环)
    - GET  /api/lock/history           历史记录 (分页查询)
    - GET  /api/mfa/status             MFA 状态
    - GET  /api/device/status          设备状态
    - GET  /api/face/logs              人脸识别日志
    - GET  /api/alarms                 告警列表
    - POST /api/mfa/open-door/request  开门发起 (会话创建 + 设备派发, 关键链路)

用法示例 (在 tests/perf 目录下, 需先安装 locust):
    pip install locust
    # 单机命令行模式, 并发 50, 每秒新增 10, 跑 3 分钟
    locust -f locustfile.py --headless -u 50 -r 10 -t 3m --host http://localhost:8000 \
        --csv=results/c50 --html=results/c50.html

数据准备:
    先运行 prepare_data.py 批量创建/审批 perf_user_001 ~ perf_user_020
    默认口令 Perf@123456, 该口令通过环境变量 PERF_USER_PASSWORD 覆盖。
"""

from __future__ import annotations

import os
import random
import time
from typing import Optional

from locust import HttpUser, between, task, events


PERF_USER_PREFIX = os.environ.get("PERF_USER_PREFIX", "perf_user_")
PERF_USER_COUNT = int(os.environ.get("PERF_USER_COUNT", "20"))
PERF_USER_PASSWORD = os.environ.get("PERF_USER_PASSWORD", "Perf@123456")
PERF_DEVICE_ID = os.environ.get("PERF_DEVICE_ID", "door_01")


def _pick_user_index() -> int:
    return random.randint(1, PERF_USER_COUNT)


class SmartLockUser(HttpUser):
    """模拟登录后一个已登录用户的常规操作组合。"""

    # 每个虚拟用户两个动作之间等待 0.5 ~ 2 秒, 更接近真实使用
    wait_time = between(0.5, 2.0)

    token: Optional[str] = None
    username: Optional[str] = None

    def on_start(self):
        """虚拟用户启动时先登录, 拿到 JWT 再进入任务循环。"""
        idx = _pick_user_index()
        self.username = f"{PERF_USER_PREFIX}{idx:03d}"
        self._login()

    def _login(self):
        payload = {"username": self.username, "password": PERF_USER_PASSWORD}
        with self.client.post(
            "/api/login",
            json=payload,
            name="POST /api/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"login failed: {resp.status_code} {resp.text[:120]}")
                self.token = None
                return
            try:
                self.token = resp.json().get("access_token")
            except ValueError:
                resp.failure("login response not json")
                self.token = None

    def _auth_headers(self) -> dict:
        if not self.token:
            self._login()
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # -------- 读接口: 高频, 权重最高 --------

    @task(8)
    def lock_status(self):
        self.client.get(
            f"/api/lock/status?device_id={PERF_DEVICE_ID}",
            headers=self._auth_headers(),
            name="GET /api/lock/status",
        )

    @task(6)
    def lock_history(self):
        page = random.randint(1, 3)
        self.client.get(
            f"/api/lock/history?page={page}&per_page=10",
            headers=self._auth_headers(),
            name="GET /api/lock/history",
        )

    @task(4)
    def mfa_status(self):
        self.client.get(
            "/api/mfa/status",
            headers=self._auth_headers(),
            name="GET /api/mfa/status",
        )

    @task(3)
    def device_status(self):
        self.client.get(
            "/api/device/status",
            headers=self._auth_headers(),
            name="GET /api/device/status",
        )

    @task(2)
    def face_logs(self):
        self.client.get(
            "/api/face/logs?page=1&per_page=10",
            headers=self._auth_headers(),
            name="GET /api/face/logs",
        )

    @task(2)
    def alarms(self):
        self.client.get(
            "/api/alarms?limit=20",
            headers=self._auth_headers(),
            name="GET /api/alarms",
        )

    # -------- 写接口: 权重较低, 避免把测试用户的锁反复翻转 --------

    @task(2)
    def toggle_lock(self):
        action = random.choice(["LOCK", "UNLOCK"])
        self.client.post(
            "/api/lock/control",
            json={"device_id": PERF_DEVICE_ID, "action": action},
            headers=self._auth_headers(),
            name="POST /api/lock/control",
        )

    @task(1)
    def open_door_request(self):
        """
        发起开门请求。要求测试用户已经绑定了 PERF_DEVICE_ID 设备。
        若返回 403 (Device not bound) 或 423 (DEVICE_LOCKED), 视为业务预期, 不算失败。
        """
        with self.client.post(
            "/api/mfa/open-door/request",
            json={"device_id": PERF_DEVICE_ID},
            headers=self._auth_headers(),
            name="POST /api/mfa/open-door/request",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 403, 423):
                resp.success()
            else:
                resp.failure(f"unexpected status {resp.status_code}: {resp.text[:120]}")


class LoginOnlyUser(HttpUser):
    """
    专测 /api/login (bcrypt) 的独立压测场景。
    Locust 支持多个 User 类共存, 但为了单独出报告, 一般单跑此类:
        locust -f locustfile.py LoginOnlyUser --headless -u 20 -r 5 -t 2m --host http://localhost:8000
    """

    wait_time = between(0.2, 1.0)

    @task
    def login(self):
        idx = _pick_user_index()
        username = f"{PERF_USER_PREFIX}{idx:03d}"
        with self.client.post(
            "/api/login",
            json={"username": username, "password": PERF_USER_PASSWORD},
            name="POST /api/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"login failed: {resp.status_code}")


# -------- 全局钩子: 打印开始/结束时间, 方便对照日志 --------

@events.test_start.add_listener
def _on_start(environment, **kwargs):
    print(f"[perf] test started at {time.strftime('%Y-%m-%d %H:%M:%S')}")


@events.test_stop.add_listener
def _on_stop(environment, **kwargs):
    print(f"[perf] test stopped at {time.strftime('%Y-%m-%d %H:%M:%S')}")
