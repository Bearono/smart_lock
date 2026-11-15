"""Local course audio console; explicit device I/O, no network or lock control."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = Path(__file__).resolve().parent
for search_path in (DEPLOY, ROOT / 'packages/smartlock_protocol'):
    if str(search_path) not in sys.path:
        sys.path.insert(0, str(search_path))

import audio_device
import audio_peer
from smartlock_protocol import acoustic_fingerprint
from smartlock_protocol.audio_d2d import BINDING_FIELDS, canonical, identity, load_public, strict_object, validate_binding


class ConsoleController:
    """Display-independent operations; every output stays in this local instance."""
    def __init__(self, directory=None, backend=None):
        self.directory = Path(directory) if directory is not None else ROOT / 'instance/audio-console'
        if self.directory.is_symlink():
            raise ValueError('本机数据目录不能是符号链接')
        self.files = self.directory / 'files'
        if self.files.is_symlink():
            raise ValueError('输出目录不能是符号链接')
        self.backend = backend
        self.peer = None
        self.receiver_public = None
        self.request = None
        self.fingerprint_model = None
        self.last_wave = None
        self.last_recording = None

    def _write(self, prefix, suffix, content):
        path = self.files / f'{prefix}-{uuid.uuid4().hex[:12]}{suffix}'
        audio_peer.write_output(path, content)
        return path

    def _issuer(self):
        if self.peer is None:
            raise ValueError('请先启用本机发行端')
        self.peer.require_role('issuer')
        return self.peer

    def initialize(self, name):
        identity(name)
        if (self.directory / 'master.key').exists() or (self.directory / 'state.sqlite3').exists():
            peer = audio_peer.Peer(self.directory)
            existing = peer.require_role('issuer')
            if existing != name:
                raise ValueError(f'本机已有身份 {existing}；请使用该名称，既有身份不会被覆盖')
        else:
            peer = audio_peer.Peer(self.directory, create=True)
            peer.initialize('issuer', name)
        self.peer = peer
        public = peer.public_key()
        return {'identity': name, 'sha256': hashlib.sha256(public).hexdigest(),
                'base64': base64.b64encode(public).decode('ascii')}

    def existing_identity(self):
        if not (self.directory / 'state.sqlite3').exists():
            return None
        return audio_peer.Peer(self.directory).require_role('issuer')

    def export_issuer(self):
        public = self._issuer().public_key()
        return {'path': self._write('issuer-public', '.der', public),
                'sha256': hashlib.sha256(public).hexdigest(),
                'base64': base64.b64encode(public).decode('ascii')}

    def preview_receiver(self, path):
        public = audio_peer.read_limited(path, 4096)
        load_public(public, 'rsa')
        return {'source': str(path), 'sha256': hashlib.sha256(public).hexdigest()}

    def pin_receiver(self, path, expected_sha256):
        public = audio_peer.read_limited(path, 4096)
        load_public(public, 'rsa')
        digest = hashlib.sha256(public).hexdigest()
        if digest != expected_sha256:
            raise ValueError('公钥文件已变化，请重新选择并核对指纹')
        saved = self._write('receiver-public', '.der', public)
        self.receiver_public = public
        return {'path': saved, 'sha256': digest}

    def load_model(self, path):
        model = json.loads(audio_peer.read_limited(path, 65536), object_pairs_hook=audio_peer.unique_object)
        if not isinstance(model, dict):
            raise ValueError('声学模型必须是对象')
        threshold = model.get('threshold')
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or threshold < 0 or not model.get('calibration'):
            raise ValueError('请选择已用独立正负样本校准的声学模型')
        acoustic_fingerprint.distance(model, model.get('center_db'))
        self.fingerprint_model = self._write('acoustic-model', '.json', canonical(model))
        return {'path': self.fingerprint_model, 'device_id': model.get('device_id', '未命名')}

    def clear_model(self):
        self.fingerprint_model = None

    def _read(self, path):
        if Path(path).suffix.lower() not in ('.wav', '.json'):
            raise ValueError('请选择 WAV 或 JSON 文件')
        return audio_peer.read_packet(path, self.fingerprint_model)

    def import_request(self, path):
        peer = self._issuer()
        request = self._read(path)
        strict_object(request, BINDING_FIELDS | {'recipient_public_key'})
        binding = validate_binding({name: request[name] for name in BINDING_FIELDS}, time.time())
        if binding['sender'] != peer.require_role('issuer'):
            raise ValueError('请求中的发行端名称与本机不一致')
        self.request = request
        return {'recipient': binding['recipient'], 'expires': binding['expires'],
                'acoustic_checked': self.fingerprint_model is not None}

    def issue(self):
        if self.receiver_public is None:
            raise ValueError('请先核对并固定手机接收公钥')
        if self.request is None:
            raise ValueError('请先导入本次手机请求')
        packet = self._issuer().issue(self.request, self.receiver_public)
        content = audio_peer.packet_bytes(Path('packet.wav'), packet)
        self.last_wave = self._write('session', '.wav', content)
        return {'path': self.last_wave, 'recipient': packet['binding']['recipient'],
                'expires': packet['binding']['expires']}

    def confirm(self, path):
        result = self._issuer().verify_confirmation(self._read(path))
        saved = self._write('confirmed', '.json', canonical(result))
        return {'path': saved, 'recipient': result['binding']['recipient'],
                'acoustic_checked': self.fingerprint_model is not None}

    def decrypt(self, path):
        plaintext = self._issuer().open_message(self._read(path))
        saved = self._write('message', '.bin', plaintext)
        try:
            text = plaintext.decode('utf-8', errors='strict')
            # Do not let terminal-like control characters masquerade as UI status.
            text = ''.join(ch if ch in '\n\r\t' or ord(ch) >= 32 else '\ufffd' for ch in text)
        except UnicodeDecodeError:
            text = f'已认证的二进制消息（{len(plaintext)} 字节），已保存。'
        return {'path': saved, 'text': text, 'acoustic_checked': self.fingerprint_model is not None}

    def devices(self):
        return audio_device.list_devices(self.backend)

    def record(self, seconds, device):
        self.last_recording = self._write('recording', '.wav', audio_device.record(seconds, device, backend=self.backend))
        return {'path': self.last_recording}

    def play(self, path, device):
        audio_device.play(audio_device.read_bounded(path), device, gain=0.2, backend=self.backend)
        return {'path': Path(path)}


class AudioConsole:
    """One worker at a time; only the Tk thread touches widgets."""
    def __init__(self, root, controller=None):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.root = tk, ttk, root
        self.controller = controller or ConsoleController()
        self.events = queue.Queue()
        self.worker = None
        self.closing = False
        self.controls = []
        self.pending_pin = None
        self.issuer_base64 = None
        self.request_expires = 0
        self.input_devices, self.output_devices = {}, {}
        root.title('SmartLock · 课程音频控制台')
        root.geometry('1120x850')
        root.minsize(900, 740)
        root.protocol('WM_DELETE_WINDOW', self.close)
        body = ttk.Frame(root, padding=18)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text='课程音频控制台', font=('', 22, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(body, text='手机密钥分发与认证消息实验 · 不控制门锁').grid(row=1, column=0, sticky='w', pady=(4, 14))

        issuer = ttk.LabelFrame(body, text='本机发行端', padding=10)
        issuer.grid(row=2, column=0, sticky='ew', pady=4)
        issuer.columnconfigure(1, weight=1)
        ttk.Label(issuer, text='本机名称').grid(row=0, column=0, padx=(0, 8))
        self.name = tk.StringVar(value='laptop')
        entry = ttk.Entry(issuer, textvariable=self.name, width=20)
        entry.grid(row=0, column=1, sticky='w')
        self.controls.append(entry)
        self.button(issuer, '启用本机', self.initialize).grid(row=0, column=2, padx=4)
        self.button(issuer, '导出公钥', lambda: self.run('导出公钥', self.controller.export_issuer, self.exported)).grid(row=0, column=3, padx=4)
        self.button(issuer, '复制公钥', self.copy_public).grid(row=0, column=4, padx=4)
        self.issuer_label = ttk.Label(issuer, text='尚未启用；已有身份会继续使用。', wraplength=1020)
        self.issuer_label.grid(row=1, column=0, columnspan=5, sticky='w', pady=(8, 0))

        receiver = ttk.LabelFrame(body, text='手机接收公钥', padding=10)
        receiver.grid(row=3, column=0, sticky='ew', pady=4)
        self.button(receiver, '选择手机公钥', self.choose_receiver).grid(row=0, column=0, padx=(0, 8))
        self.button(receiver, '核对并固定', self.pin_receiver).grid(row=0, column=1)
        self.receiver_label = ttk.Label(receiver, text='先选择手机导出的 DER 公钥，再与手机屏幕上的 SHA-256 核对。', wraplength=1010)
        self.receiver_label.grid(row=1, column=0, columnspan=3, sticky='w', pady=(8, 0))

        flow = ttk.LabelFrame(body, text='密钥与消息', padding=10)
        flow.grid(row=4, column=0, sticky='ew', pady=4)
        actions = [('导入请求', self.choose_request), ('签发密钥 WAV', lambda: self.run('签发密钥', self.controller.issue, self.issued)),
                   ('验证确认', lambda: self.choose_incoming('confirm')), ('解密消息', lambda: self.choose_incoming('decrypt'))]
        for column, (label, action) in enumerate(actions):
            self.button(flow, label, action).grid(row=0, column=column, padx=(0, 10))
        self.request_label = ttk.Label(flow, text='等待手机请求。每次手机重新生成请求后，都需要核对新的接收公钥。')
        self.request_label.grid(row=1, column=0, columnspan=4, sticky='w', pady=(8, 0))
        self.countdown = ttk.Label(flow, text='')
        self.countdown.grid(row=2, column=0, columnspan=4, sticky='w')

        audio = ttk.LabelFrame(body, text='录音与播放', padding=10)
        audio.grid(row=5, column=0, sticky='ew', pady=4)
        audio.columnconfigure(1, weight=1)
        ttk.Label(audio, text='麦克风').grid(row=0, column=0, sticky='w')
        self.input_box = ttk.Combobox(audio, state='readonly', width=58)
        self.input_box.grid(row=0, column=1, sticky='ew', padx=8)
        ttk.Label(audio, text='扬声器').grid(row=1, column=0, sticky='w', pady=(8, 0))
        self.output_box = ttk.Combobox(audio, state='readonly', width=58)
        self.output_box.grid(row=1, column=1, sticky='ew', padx=8, pady=(8, 0))
        self.button(audio, '刷新设备', lambda: self.run('读取音频设备', self.controller.devices, self.devices_loaded)).grid(row=0, column=2)
        self.seconds = tk.StringVar(value='5')
        spin = ttk.Spinbox(audio, from_=0.1, to=10, increment=0.5, textvariable=self.seconds, width=5)
        spin.grid(row=0, column=3, padx=(12, 4))
        self.controls.append(spin)
        ttk.Label(audio, text='秒').grid(row=0, column=4)
        self.button(audio, '录音', self.record).grid(row=0, column=5, padx=8)
        self.button(audio, '播放 WAV', self.play).grid(row=1, column=2, pady=(8, 0))
        self.button(audio, '播放密钥', self.play_session).grid(row=1, column=3, columnspan=3, pady=(8, 0))
        ttk.Label(audio, text='录音最多 10 秒；设备无响应时另留 3 秒清理。所有音频由你手动启动。').grid(row=2, column=0, columnspan=6, sticky='w', pady=(8, 0))

        acoustic = ttk.Frame(body)
        acoustic.grid(row=6, column=0, sticky='ew', pady=8)
        self.button(acoustic, '载入声学模型', self.choose_model).pack(side='left')
        self.button(acoustic, '关闭声学匹配', self.clear_model).pack(side='left', padx=8)
        self.model_label = ttk.Label(acoustic, text='仅密码认证；未配置声学匹配。', wraplength=700)
        self.model_label.pack(side='left')

        self.status = ttk.Label(body, text='就绪', wraplength=1040)
        self.status.grid(row=7, column=0, sticky='ew', pady=(4, 8))
        self.message = tk.Text(body, height=8, wrap='word', state='disabled', font=('', 12))
        self.message.grid(row=8, column=0, sticky='nsew')
        body.rowconfigure(8, weight=1)
        ttk.Label(body, text='所有输出保存在：' + str(self.controller.files), wraplength=1040).grid(row=9, column=0, sticky='w', pady=(8, 0))
        root.after(75, self.poll)
        self.run('检查本机身份', self.controller.existing_identity, self.restore_identity)

    def button(self, parent, text, command):
        widget = self.ttk.Button(parent, text=text, command=command)
        self.controls.append(widget)
        return widget

    def busy(self, value):
        for widget in self.controls:
            widget.configure(state='disabled' if value else 'normal')
        for box in (self.input_box, self.output_box):
            box.configure(state='disabled' if value else 'readonly')

    def run(self, label, operation, completed):
        if self.closing or self.worker is not None:
            return
        self.busy(True)
        self.status.configure(text=label + '…')
        def work():
            try:
                result = operation()
            except Exception as error:
                self.events.put(('error', str(error), None))
            else:
                self.events.put(('ok', result, completed))
        self.worker = threading.Thread(target=work, name='smartlock-audio-console', daemon=False)
        self.worker.start()

    def poll(self):
        if self.worker is not None and not self.worker.is_alive():
            self.worker.join()
            self.worker = None
            if self.closing:
                self.root.destroy()
                return
            self.busy(False)
            try:
                kind, value, completed = self.events.get_nowait()
                if kind == 'error':
                    self.status.configure(text='操作未完成：' + value)
                else:
                    completed(value)
            except queue.Empty:
                pass
        if self.request_expires:
            seconds = max(0, self.request_expires - int(time.time()))
            self.countdown.configure(text=f'本次请求剩余 {seconds} 秒' if seconds else '本次请求已到期，请在手机上重新生成。')
        self.root.after(75, self.poll)

    def close(self):
        if self.worker is not None and self.worker.is_alive():
            self.closing = True
            self.busy(True)
            self.status.configure(text='正在收尾后退出：录音最多 10 秒，设备超时另留 3 秒；不会遗留后台任务。')
        else:
            self.root.destroy()

    def choose(self, title, types):
        from tkinter import filedialog
        return filedialog.askopenfilename(parent=self.root, title=title, filetypes=types,
                                          initialdir=str(self.controller.files if self.controller.files.exists() else ROOT))

    def initialize(self):
        name = self.name.get().strip()
        self.run('启用本机', lambda: self.controller.initialize(name), self.initialized)

    def restore_identity(self, name):
        if name:
            self.name.set(name)
            self.initialize()
        else:
            self.status.configure(text='输入发行端名称并启用本机，然后将公钥传给手机。')

    def initialized(self, value):
        self.issuer_base64 = value['base64']
        self.issuer_label.configure(text=f"已启用 {value['identity']} · SHA-256：{value['sha256']}")
        self.status.configure(text='本机已就绪。将发行端公钥传给手机并核对指纹。')

    def exported(self, value):
        self.issuer_base64 = value['base64']
        self.status.configure(text='发行端公钥已导出：' + str(value['path']))

    def copy_public(self):
        if not self.issuer_base64:
            self.status.configure(text='请先启用本机。')
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.issuer_base64)
        self.status.configure(text='发行端公钥已复制，可粘贴到手机；请同时核对 SHA-256。')

    def choose_receiver(self):
        path = self.choose('选择手机导出的接收公钥', [('公钥 DER', '*.der'), ('所有文件', '*')])
        if path:
            self.run('读取手机公钥', lambda: self.controller.preview_receiver(path), self.receiver_previewed)

    def receiver_previewed(self, value):
        self.pending_pin = value
        self.receiver_label.configure(text='待核对 SHA-256：' + value['sha256'])
        self.status.configure(text='请与手机显示的接收方公钥指纹逐一核对，匹配后点击“核对并固定”。')

    def pin_receiver(self):
        if not self.pending_pin:
            self.status.configure(text='请先选择手机接收公钥。')
            return
        value = dict(self.pending_pin)
        self.run('固定手机公钥', lambda: self.controller.pin_receiver(value['source'], value['sha256']), self.receiver_pinned)

    def receiver_pinned(self, value):
        self.receiver_label.configure(text='已固定 SHA-256：' + value['sha256'])
        self.status.configure(text='手机公钥已固定。可导入本次请求并签发。')

    def choose_request(self):
        path = self.choose('导入手机请求', [('请求', '*.wav *.json')])
        if path:
            self.run('读取请求', lambda: self.controller.import_request(path), self.request_loaded)

    def request_loaded(self, value):
        self.request_expires = value['expires']
        self.request_label.configure(text='接收方：' + value['recipient'])
        self.status.configure(text='请求已载入，请确认手机公钥已固定，再签发密钥 WAV。')

    def issued(self, value):
        self.request_expires = value['expires']
        self.status.configure(text='密钥 WAV 已生成，可传给手机或点击“播放密钥”：' + str(value['path']))

    def choose_incoming(self, kind):
        path = self.choose('选择确认音频' if kind == 'confirm' else '选择加密消息音频', [('音频或消息', '*.wav *.json')])
        if path:
            operation = self.controller.confirm if kind == 'confirm' else self.controller.decrypt
            completed = self.confirmed if kind == 'confirm' else self.decrypted
            self.run('验证密钥确认' if kind == 'confirm' else '认证并解密', lambda: operation(path), completed)

    def confirmed(self, value):
        self.status.configure(text='密钥确认通过，接收方：' + value['recipient'] + '。现在可接收认证消息。')

    def decrypted(self, value):
        self.message.configure(state='normal')
        self.message.delete('1.0', 'end')
        self.message.insert('1.0', value['text'])
        self.message.configure(state='disabled')
        assurance = '密码认证与附加声学匹配通过' if value['acoustic_checked'] else '密码认证通过（未配置声学匹配）'
        self.status.configure(text=assurance + '。消息已保存：' + str(value['path']))

    def devices_loaded(self, devices):
        self.input_devices = {f"{row['index']} · {row['name']}": row['index'] for row in devices if row['max_input_channels'] > 0}
        self.output_devices = {f"{row['index']} · {row['name']}": row['index'] for row in devices if row['max_output_channels'] > 0}
        self.input_box.configure(values=list(self.input_devices))
        self.output_box.configure(values=list(self.output_devices))
        self.input_box.set('')
        self.output_box.set('')
        self.status.configure(text='请选择麦克风和扬声器；刷新后不会自动启用任何设备。')

    def record(self):
        device = self.input_devices.get(self.input_box.get())
        try:
            seconds = float(self.seconds.get())
        except ValueError:
            self.status.configure(text='录音时长应为 0.1–10 秒。')
            return
        self.run('正在录音', lambda: self.controller.record(seconds, device), self.recorded)

    def recorded(self, value):
        self.status.configure(text='录音已保存，可在“导入请求”“验证确认”或“解密消息”中选择：' + str(value['path']))

    def play(self):
        path = self.choose('选择要播放的 WAV', [('WAV 音频', '*.wav')])
        if path:
            self.play_path(path)

    def play_session(self):
        if self.controller.last_wave is None:
            self.status.configure(text='请先签发密钥 WAV。')
            return
        self.play_path(self.controller.last_wave)

    def play_path(self, path):
        device = self.output_devices.get(self.output_box.get())
        self.run('正在播放', lambda: self.controller.play(path, device),
                 lambda value: self.status.configure(text='播放完成：' + str(value['path'])))

    def choose_model(self):
        path = self.choose('选择已校准的声学模型', [('JSON 模型', '*.json')])
        if path:
            self.run('载入声学模型', lambda: self.controller.load_model(path), self.model_loaded)

    def model_loaded(self, value):
        self.model_label.configure(text='已启用附加声学匹配：' + str(value['device_id']) + '；所有接收文件须为 WAV。密码验证仍必需。')
        self.status.configure(text='声学匹配描述发声设备、麦克风与房间路径，不是独立可信身份。')

    def clear_model(self):
        self.controller.clear_model()
        self.model_label.configure(text='仅密码认证；未配置声学匹配。')
        self.status.configure(text='已关闭附加声学匹配。')


def main():
    # Packaged Windows Python may not expose Tcl resources to native Tcl's file
    # loader. A project-local copy from the same runtime is used when present.
    local_tcl = Path(sys.prefix) / 'tcl'
    if sys.platform == 'win32' and (local_tcl / 'tcl8.6/init.tcl').is_file() and (local_tcl / 'tk8.6/tk.tcl').is_file():
        os.environ.setdefault('TCL_LIBRARY', str(local_tcl / 'tcl8.6'))
        os.environ.setdefault('TK_LIBRARY', str(local_tcl / 'tk8.6'))
    import tkinter as tk
    root = tk.Tk()
    AudioConsole(root)
    root.mainloop()


if __name__ == '__main__':
    main()
