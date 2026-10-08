"""Read-only operational facts. Reports are generated offline, never executed by HTTP."""
from datetime import datetime, timezone
from flask import current_app
from app.models import DeviceSecuritySession, SecureMessageReceipt, DoorCommand
from pathlib import Path
import json


def verification_report():
    path = Path(current_app.config['SECURITY_REPORT_PATH'])
    try:
        if path.stat().st_size > 64 * 1024:
            return None
        report = json.loads(path.read_text(encoding='utf-8'))
        keys = ('created_at', 'scope', 'git_sha', 'source_digest', 'environment')
        if not isinstance(report, dict) or type(report.get('passed')) is not bool or any(not isinstance(report.get(key), str) for key in keys):
            return None
        checks = report.get('checks')
        if not isinstance(checks, list) or len(checks) > 30:
            return None
        clean = []
        for check in checks:
            if not isinstance(check, dict) or not isinstance(check.get('name'), str) or type(check.get('exit_code')) is not int:
                return None
            clean.append({'name': check['name'], 'exit_code': check['exit_code']})
        return {**{key: report[key] for key in keys}, 'passed': report['passed'], 'checks': clean}
    except (OSError, ValueError, TypeError):
        return None


def evidence():
    return {
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'verification': verification_report(),
        'protocol': {'handshake': 'SPAKE2 + 双向密钥确认', 'envelope': 'AES-256-GCM；v2 对照为 CBC + HMAC',
                     'version': 'SL-SEC-v3', 'v2_enabled': bool(current_app.config['ALLOW_PROTOCOL_V2']),
                     'legacy_upload_enabled': bool(current_app.config['ALLOW_LEGACY_SECURE_UPLOAD']),
                     'constant_time_pake': False},
        'controls': [
            {'name': '登录身份', 'detail': '账户密码 + TOTP；后端逐请求检查会话与审批状态'},
            {'name': '设备权限', 'detail': '管理员授予访问权限 + 用户认证绑定'},
            {'name': '消息重放', 'detail': '数据库唯一约束保存会话、请求 ID 与 nonce'},
            {'name': '命令生命周期', 'detail': '短期有效，执行回执与最近状态分开'},
            {'name': '图片隐私', 'detail': '授权后读取私有目录图片；不存在公开静态图片入口'},
        ],
        'storage': {'sessions': DeviceSecuritySession.query.count(),
                    'receipts': SecureMessageReceipt.query.count(), 'commands': DoorCommand.query.count()},
        'limitations': ['python-spake2 不承诺常数时间实现，不能宣称生产级认证。',
                        '页面不能证明树莓派实机性能、锁具反馈或远程 TLS 部署已验收。'],
    }
