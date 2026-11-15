"""Operator-started, loopback-only camera test console. Never authorizes a door command."""

import argparse
import base64
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import subprocess
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).resolve().parent / "device_console"
LABELS = {
    "live_front",
    "live_angle",
    "live_dim",
    "screen_photo",
    "print_photo",
    "empty",
    "multiple",
}


def command_json(command, *, script=None, timeout=45):
    result = subprocess.run(
        command,
        input=script.encode() if script else None,
        capture_output=True,
        timeout=timeout,
        cwd=ROOT,
    )
    if result.returncode:
        raise RuntimeError("设备操作失败，请检查设备服务与连接。")
    if len(result.stdout) > 12 * 1024 * 1024:
        raise RuntimeError("设备返回数据超出限制。")
    return json.loads(result.stdout)


class CameraController:
    def __init__(self, device_id, ssh, remote_root):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", device_id):
            raise ValueError("Invalid device ID")
        if not re.fullmatch(r"/[A-Za-z0-9_/.-]+", remote_root):
            raise ValueError("Invalid remote installation path")
        self.device_id, self.ssh, self.remote_root = device_id, ssh, remote_root

    def capture(self):
        script = (
            "device_id="
            + repr(self.device_id)
            + "\n"
            + """
import base64,json,time
from pathlib import Path
import requests
from app import create_app,db
from app.models import DeviceProvisioning,MediaAsset
from app.device_commands import signed_command
from app.media_storage import unprotect
from app.time_contract import timestamp
app=create_app()
with app.app_context():
 p=DeviceProvisioning.query.filter_by(device_id=device_id,enabled=True).one()
 body,headers=signed_command(device_id,'/capture_and_send',{})
 origin=p.service_url
 db.session.rollback()
 started=time.monotonic()
 r=requests.post(origin+'/capture_and_send',data=body,headers=headers,timeout=15,allow_redirects=False)
 r.raise_for_status()
 reply=r.json()
 if reply.get('status') != 'image_sent': raise ValueError('Capture not confirmed')
 filename=reply['info']['snapshot'].rsplit('/',1)[-1]
 asset=db.session.get(MediaAsset,filename)
 if not asset or asset.device_id!=device_id: raise ValueError('Invalid capture receipt')
 raw=unprotect((Path(app.config['UPLOAD_FOLDER'])/filename).read_bytes(),filename,device_id)
 print(json.dumps({'image64':base64.b64encode(raw).decode(),'received_at':timestamp(asset.created_at),
                   'capture_seconds':round(time.monotonic()-started,3),'snapshot':reply['info']['snapshot']}))
"""
        )
        result = command_json(
            [
                "docker",
                "compose",
                "-f",
                "compose.yaml",
                "-f",
                "compose.tls.yaml",
                "exec",
                "-T",
                "backend",
                "python",
                "-c",
                script,
            ],
            timeout=25,
        )
        image = base64.b64decode(result.pop("image64"), validate=True)
        if not 0 < len(image) <= 8 * 1024 * 1024:
            raise ValueError("Invalid image size")
        return result, image

    def analyze(self, image):
        # Same deployed models and template store; score the saved JPEG, not an unlock challenge.
        script = (
            "root_name="
            + repr(self.remote_root)
            + "\nimage64="
            + repr(base64.b64encode(image).decode())
            + "\n"
            + """
import base64,json,os,sys,time
from pathlib import Path
root=Path(root_name)
for line in (root/'deploy/.env').read_text().splitlines():
 key,sep,value=line.partition('=')
 if sep and key in ('SMART_LOCK_MODELS_DIR','SMART_LOCK_TEMPLATES_DIR'):
  os.environ[key]=value.strip().strip(chr(34)).strip(chr(39))
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
sys.path.insert(0,str(root/'apps/device/cv/code'))
import cv2,numpy as np
from recognize import recognize_with_pad,_get_detector
from model_manifest import verify_models
from paths import models_dir
verify_models(models_dir())
frame=cv2.imdecode(np.frombuffer(base64.b64decode(image64),dtype=np.uint8),cv2.IMREAD_COLOR)
start=time.monotonic()
faces=_get_detector().detect(frame)
identity,similarity,pad=recognize_with_pad(frame)
print(json.dumps({'face_count':len(faces),'identity':identity,'similarity':similarity,'pad_score':pad,
                  'analysis_seconds':round(time.monotonic()-start,3)}))
"""
        )
        return command_json(
            self.ssh + [self.remote_root + "/.venv-pi/bin/python -"], script=script, timeout=40
        )


class ConsoleState:
    def __init__(self, controller, directory, expected="admin"):
        self.controller, self.directory, self.expected = controller, Path(directory), expected
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.busy, self.phase, self.error = False, "idle", ""
        self.history = []
        self.token = secrets.token_urlsafe(32)

    def snapshot(self):
        with self.lock:
            return json.loads(
                json.dumps(
                    {
                        "busy": self.busy,
                        "phase": self.phase,
                        "error": self.error,
                        "history": self.history,
                        "expected": self.expected,
                    }
                )
            )

    def start(self, label):
        if label not in LABELS:
            raise ValueError("Invalid sample label")
        with self.lock:
            if self.busy:
                return False
            self.busy, self.phase, self.error = True, "capturing", ""
        threading.Thread(
            target=self._capture, args=(label,), name="camera-test", daemon=False
        ).start()
        return True

    def _capture(self, label):
        sample = {
            "id": uuid.uuid4().hex,
            "label": label,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "scope": "saved_camera_jpeg_diagnostic_not_door_authorization",
            "status": "capturing",
        }
        try:
            receipt, image = self.controller.capture()
            sample.update(receipt)
            (self.directory / (sample["id"] + ".jpg")).write_bytes(image)
            sample["status"] = "analyzing"
            with self.lock:
                self.phase = "analyzing"
                self.history.insert(0, dict(sample))
                self.history = self.history[:100]
            result = self.controller.analyze(image)
            sample["analysis"] = result
            sample["sample_passed"] = (
                result["face_count"] == 1
                and result["identity"] == self.expected
                and result["similarity"] >= 0.90
                and result["pad_score"] >= 0.80
            )
            sample["status"] = "complete"
        except Exception as exc:
            sample["status"] = "failed"
            sample["error"] = "拍摄或检测未完成，请检查相机连接后重试。"
            sample["error_type"] = type(exc).__name__
        finally:
            sample["finished_at"] = datetime.now(timezone.utc).isoformat()
            try:
                (self.directory / (sample["id"] + ".json")).write_text(
                    json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except OSError:
                sample["error"] = "测试记录未能保存，请检查本机磁盘。"
                sample["status"] = "failed"
            with self.lock:
                self.history = [item for item in self.history if item["id"] != sample["id"]]
                self.history.insert(0, sample)
                self.history = self.history[:100]
                self.busy, self.phase, self.error = False, sample["status"], sample.get("error", "")


def make_handler(state, origin):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, kind="application/json"):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            for key, value in {
                "Content-Type": kind,
                "Content-Length": str(len(body)),
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            }.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            if self.headers.get("Host") != origin.removeprefix("http://"):
                self.send(403, {"error": "Loopback host required"})
                return False
            return True

        def do_GET(self):
            if not self.valid_host():
                return
            if self.path == "/api/state":
                return self.send(200, {**state.snapshot(), "csrf": state.token})
            static = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if self.path in static:
                name, kind = static[self.path]
                return self.send(200, (ASSETS / name).read_bytes(), kind)
            match = re.fullmatch(r"/image/([0-9a-f]{32})", self.path)
            if match and any(item["id"] == match[1] for item in state.snapshot()["history"]):
                path = state.directory / (match[1] + ".jpg")
                if path.is_file():
                    return self.send(200, path.read_bytes(), "image/jpeg")
            self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.valid_host():
                return
            if self.headers.get("Origin") != origin or not secrets.compare_digest(
                self.headers.get("X-Test-CSRF", ""), state.token
            ):
                return self.send(403, {"error": "Local console request required"})
            if self.path != "/api/capture":
                return self.send(404, {"error": "Not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 256 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Invalid request")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or set(data) != {"label"}:
                    raise ValueError("Invalid request")
                accepted = state.start(data["label"])
            except (ValueError, TypeError):
                return self.send(400, {"error": "Invalid sample"})
            self.send(202 if accepted else 409, {"accepted": accepted})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="pi_csi_01")
    parser.add_argument("--expected-user", default="admin")
    parser.add_argument("--ssh-target", required=True)
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--ssh-bind")
    parser.add_argument("--ssh-host-alias")
    parser.add_argument("--remote-root", default="/home/taylor/smart-lock")
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--output", type=Path, default=ROOT / "instance/device-console")
    args = parser.parse_args()
    if (
        not 1024 <= args.port <= 65535
        or not re.fullmatch(r"[A-Za-z0-9_.@-]+", args.ssh_target)
        or args.ssh_target.startswith("-")
    ):
        parser.error("Invalid port or SSH target")
    ssh = [
        "ssh",
        "-i",
        str(args.ssh_key.resolve()),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=5",
    ]
    if args.ssh_bind:
        ssh += ["-b", args.ssh_bind]
    if args.ssh_host_alias:
        ssh += ["-o", "HostKeyAlias=" + args.ssh_host_alias]
    ssh += [args.ssh_target]
    origin = f"http://127.0.0.1:{args.port}"
    state = ConsoleState(
        CameraController(args.device_id, ssh, args.remote_root), args.output, args.expected_user
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state, origin))
    server.daemon_threads = True
    print("Camera test console: " + origin, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
