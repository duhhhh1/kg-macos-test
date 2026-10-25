#!/usr/bin/env python3
"""A bounded, authenticated screen and input bridge for this ephemeral Mac."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import platform
import re
import secrets
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from urllib.request import urlopen

try:
    from . import inspect_commission_atrust as inspection
    from . import login_commission_atrust as login
    from . import run_commission_macos_actions as native
except ImportError:
    import inspect_commission_atrust as inspection
    import login_commission_atrust as login
    import run_commission_macos_actions as native

TUNNEL_URL = 'https://github.com/cloudflare/cloudflared/releases/download/2026.10.3/cloudflared-darwin-arm64.tgz'
TUNNEL_SHA = '1165d14b6f6360a3b8c283d7d1100024d6ec7cd9bc9e32519e96150645f3ec55'
UI = Path(__file__).with_name('macos-manual-ui')
KEYS = {'Enter': 36, 'Tab': 48, 'Backspace': 51, 'Escape': 53, 'Delete': 117,
        'ArrowLeft': 123, 'ArrowRight': 124, 'ArrowDown': 125, 'ArrowUp': 126,
        'Home': 115, 'End': 119, 'PageUp': 116, 'PageDown': 121, 'Space': 49}


def save(path, value):
    native.save(path, value)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def token_for(master, run_id, attempt):
    return hmac.new(master.encode(), f'{run_id}:{attempt}'.encode(), hashlib.sha256).hexdigest()


def campus_ready(host, port):
    try:
        with socket.create_connection((host, port), timeout=3) as connection:
            connection.settimeout(3)
            return connection.recv(120).startswith(b'SSH-')
    except OSError:
        return False


def perform_input(value):
    """Only normal pointer/keyboard events; no command execution from the UI."""
    action = value.get('action')
    env = dict(os.environ)
    if action in ('click', 'doubleclick'):
        x, y = value.get('x'), value.get('y')
        if not all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 8192 for n in (x, y)):
            raise ValueError('点击坐标无效')
        command = ['osascript', '-e', f'tell application "System Events" to click at {{{x}, {y}}}']
    elif action in ('text', 'key'):
        modifiers = value.get('modifiers', [])
        allowed = {'command down', 'control down', 'option down', 'shift down'}
        if not isinstance(modifiers, list) or any(m not in allowed for m in modifiers):
            raise ValueError('快捷键无效')
        code = 'var s=Application("System Events"); var v=JSON.parse(String($.getenv("KG_MANUAL_INPUT"))); '
        if action == 'text':
            text = value.get('text')
            if not isinstance(text, str) or not 1 <= len(text) <= 256:
                raise ValueError('每次输入限1至256个字符')
            code += 's.keystroke(v.text,{using:v.modifiers||[]});'
        else:
            key = value.get('key', '')
            if key in KEYS:
                value = {**value, 'code': KEYS[key]}
                code += 's.keyCode(v.code,{using:v.modifiers||[]});'
            elif isinstance(key, str) and len(key) == 1 and ord(key) >= 32:
                code += 's.keystroke(v.key,{using:v.modifiers||[]});'
            else:
                raise ValueError('不支持这个按键')
        env['KG_MANUAL_INPUT'] = json.dumps(value, ensure_ascii=False)
        command = ['osascript', '-l', 'JavaScript', '-e', "ObjC.import('stdlib');" + code]
    else:
        raise ValueError('不支持这个操作')
    for _ in range(2 if action == 'doubleclick' else 1):
        result = subprocess.run(command, env=env, capture_output=True, timeout=15)
        if result.returncode:
            raise RuntimeError('Mac未完成此操作，请检查远程画面和系统授权提示')


def handler_for(folder, config):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log text input, credentials, authorization or images.

        def send(self, data, kind='application/json', status=200):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            given = self.headers.get('Authorization', '')
            return hmac.compare_digest(given.encode('utf-8'), ('Bearer ' + config['token']).encode('utf-8'))

        def do_GET(self):
            try:
                path = self.path.split('?', 1)[0]
                if path in ('/', '/app.js', '/style.css'):
                    filename, kind = {'/': ('index.html', 'text/html; charset=utf-8'),
                                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                                      '/style.css': ('style.css', 'text/css; charset=utf-8')}[path]
                    return self.send((UI / filename).read_bytes(), kind)
                if not self.authorized():
                    return self.send({'error': '请从现有工作台的人工操作按钮进入本轮Mac'}, status=401)
                if path == '/status':
                    state = read(folder / 'status.json')
                    return self.send({**state, 'expires_at': config['expires_at'], 'screen_width': config['screen_width'],
                                      'screen_height': config['screen_height']})
                if path == '/screen':
                    picture = folder / 'screen.jpg'
                    if not picture.is_file():
                        return self.send({'error': '画面正在准备，请稍候'}, status=503)
                    return self.send(picture.read_bytes(), 'image/jpeg')
                return self.send({'error': '没有这个接口'}, status=404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send({'error': '画面暂时不可用，请稍候再试'}, status=503)

        def do_POST(self):
            if not self.authorized():
                return self.send({'error': '本轮访问认证无效'}, status=401)
            origin = self.headers.get('Origin', '')
            expected = 'https://' + self.headers.get('Host', '')
            if origin and origin != expected:
                return self.send({'error': '请在本轮远程页面内操作'}, status=403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8192:
                    raise ValueError('请求大小无效')
                value = json.loads(self.rfile.read(length))
                path = self.path.split('?', 1)[0]
                with lock:
                    state = read(folder / 'status.json')
                    if path == '/input':
                        if state['stage'] != 'manual_login':
                            raise ValueError('人工操作已结束，正在执行项目测试')
                        perform_input(value)
                        return self.send({'ok': True})
                    if path in ('/check', '/continue'):
                        ready = campus_ready(config['ssh_host'], config['ssh_port'])
                        state.update(campus_ssh_reachable=ready)
                        save(folder / 'status.json', state)
                        if path == '/continue':
                            if not ready:
                                raise ValueError('校园网SSH尚未连通。请完成学校认证，并确认aTrust已连接后再试。')
                            save(folder / 'continue.json', {'requested_at': datetime.now(timezone.utc).isoformat()})
                        return self.send({'ok': True, 'campus_ssh_reachable': ready})
                    if path == '/stop':
                        if state['stage'] != 'manual_login':
                            raise ValueError('原生测试正在运行，请在工作台查看进度')
                        save(folder / 'stop.json', {'requested': True})
                        return self.send({'ok': True})
                return self.send({'error': '没有这个操作'}, status=404)
            except (ValueError, RuntimeError, subprocess.SubprocessError):
                # Never include native command text or a submitted input value.
                return self.send({'error': '操作未完成。请查看画面提示；继续测试前需要aTrust已连接且校园网SSH可达。'}, status=400)

    return Handler


def serve(folder):
    config = read(folder / 'private.json')
    os.umask(0o077)
    server = ThreadingHTTPServer(('127.0.0.1', config['port']), handler_for(folder, config))
    stopped = threading.Event()

    def pictures():
        while not stopped.is_set():
            temp = folder / 'screen-next.jpg'
            result = subprocess.run(['screencapture', '-x', '-t', 'jpg', str(temp)], capture_output=True, timeout=15)
            if result.returncode == 0 and temp.is_file():
                os.replace(temp, folder / 'screen.jpg')
            stopped.wait(1.2)

    threading.Thread(target=pictures, daemon=True).start()
    server.timeout = 1
    deadline = datetime.fromisoformat(config['expires_at']).timestamp()
    try:
        while time.time() < deadline:
            server.handle_request()
    finally:
        stopped.set()
        server.server_close()


def prepare(state):
    if platform.system() != 'Darwin':
        raise ValueError('人工Mac入口必须在真实macOS上启动')
    master = os.environ.pop('KG_MANUAL_ACCESS_TOKEN', '')
    for name in ('HIT_VPN_USERNAME', 'HIT_VPN_PASSWORD', 'KG_CI_SSH_KEY', 'KG_CI_SSH_KNOWN_HOSTS'):
        os.environ.pop(name, None)
    if len(master) < 32:
        raise ValueError('请先配置专用的KG_MANUAL_ACCESS_TOKEN Secret')
    os.umask(0o077)
    state.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='kg-manual-mac-'))
    save(state / 'private-path.json', {'folder': str(folder)})
    if inspection.main(['--output', 'ci-public']):
        raise RuntimeError('学校客户端安装或启动未通过，请查看预检日志')
    try:
        login.ui('connect')
        for _ in range(4):
            view = login.ui('inspect')
            if view.get('theme_update'):
                login.ui('dismiss-theme')
            elif view.get('cas_entry'):
                login.ui('cas-entry')
                break
            time.sleep(2)
    except Exception:
        print('客户端已启动，剩余入口操作可在人工画面完成。', flush=True)
    with urlopen(TUNNEL_URL, timeout=120) as source:
        raw = source.read(40 * 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != TUNNEL_SHA:
        raise ValueError('临时HTTPS连接程序的SHA256校验不匹配')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as bundle:
        member = next(m for m in bundle.getmembers() if m.name in ('cloudflared', './cloudflared') and m.isfile())
        binary = folder / 'cloudflared'
        binary.write_bytes(bundle.extractfile(member).read())
        binary.chmod(0o700)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    # Actual macOS display coordinates, rather than JPEG pixel assumptions.
    size = subprocess.run(['swift', '-e', 'import AppKit; let s=NSScreen.main!.frame.size; print("\\(Int(s.width)) \\(Int(s.height))")'],
                          capture_output=True, text=True, timeout=90)
    width, height = map(int, size.stdout.strip().split())
    run_id, attempt = os.environ['GITHUB_RUN_ID'], os.environ.get('GITHUB_RUN_ATTEMPT', '1')
    expires = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
    config = {'token': token_for(master, run_id, attempt), 'port': port, 'expires_at': expires,
              'screen_width': width, 'screen_height': height,
              'ssh_host': os.environ.get('KG_SSH_HOST', 'tibaiot.7766.org'),
              'ssh_port': int(os.environ.get('KG_SSH_PORT', '60005'))}
    master = ''
    save(folder / 'private.json', config)
    save(folder / 'status.json', {'stage': 'manual_login', 'campus_ssh_reachable': False})
    logs = (folder / 'bridge.log').open('ab')
    bridge = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), 'serve', '--state', str(folder)],
                              stdout=logs, stderr=subprocess.STDOUT, start_new_session=True)
    tunnel_log = (folder / 'tunnel.log').open('ab')
    tunnel = subprocess.Popen([str(binary), 'tunnel', '--url', f'http://127.0.0.1:{port}',
                               '--no-autoupdate', '--protocol', 'http2'],
                              stdout=tunnel_log, stderr=subprocess.STDOUT, start_new_session=True)
    save(folder / 'processes.json', {'bridge': bridge.pid, 'tunnel': tunnel.pid})
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        text = (folder / 'tunnel.log').read_text(errors='replace')
        matches = re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com', text)
        if matches:
            session = {'schema': 'commission-macos-manual-v1', 'github_run_id': run_id,
                       'run_attempt': int(attempt), 'url': matches[-1], 'expires_at': expires,
                       'actual_system': 'Darwin', 'mac_version': platform.mac_ver()[0],
                       'architecture': platform.machine(), 'credentials_automatically_entered': False}
            save(Path('ci-public/manual-session.json'), session)
            summary = {'schema': 'commission-macos-actions-v1', 'phase': 'atrust-manual',
                       'status': 'manual_login_ready', 'stage': 'manual_login', 'native_completed': False,
                       'dashboard_imported': False, 'credentials_used': False,
                       'actual_system': 'Darwin', 'mac_version': platform.mac_ver()[0], 'architecture': platform.machine()}
            save(Path('ci-public/summary.json'), summary)
            print('人工Mac画面已准备；从原工作台的受保护入口进入。', flush=True)
            return 0
        if tunnel.poll() is not None or bridge.poll() is not None:
            raise RuntimeError('人工界面或HTTPS连接未能启动')
        time.sleep(1)
    raise RuntimeError('限时HTTPS入口未能准备完成')


def cleanup(folder):
    try:
        processes = read(folder / 'processes.json')
        for pid in processes.values():
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
        # Destroy private screen cache and the per-run access key.
        import shutil
        shutil.rmtree(folder)
    except (OSError, ValueError):
        pass


def wait(state, timeout):
    folder = Path(read(state / 'private-path.json')['folder'])
    ssh_credentials = {key: os.environ.pop(key, '') for key in ('KG_CI_SSH_KEY', 'KG_CI_SSH_KNOWN_HOSTS')}
    for key in ('HIT_VPN_USERNAME', 'HIT_VPN_PASSWORD', 'KG_MANUAL_ACCESS_TOKEN'):
        os.environ.pop(key, None)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if (folder / 'stop.json').is_file():
                raise RuntimeError('本轮由人工结束，未执行原生项目测试')
            if (folder / 'continue.json').is_file():
                config = read(folder / 'private.json')
                if not campus_ready(config['ssh_host'], config['ssh_port']):
                    (folder / 'continue.json').unlink()
                    continue
                save(folder / 'status.json', {'stage': 'testing', 'campus_ssh_reachable': True})
                os.environ.update(ssh_credentials)
                ssh_credentials.clear()
                print('人工登录后校园网SSH已可达，继续双向SSH及原生项目测试。', flush=True)
                return native.main(['--output', 'ci-results'])
            time.sleep(2)
        raise RuntimeError('人工操作等待时间已结束，未执行原生项目测试')
    except Exception as error:
        save(Path('ci-public/summary.json'), {'schema': 'commission-macos-actions-v1', 'phase': 'atrust-manual',
             'status': 'failed', 'stage': 'manual_login', 'native_completed': False, 'dashboard_imported': False,
             'actual_system': platform.system(), 'mac_version': platform.mac_ver()[0], 'error': str(error)})
        print(str(error), flush=True)
        return 1
    finally:
        ssh_credentials.clear()
        cleanup(folder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'serve', 'wait', 'cleanup'))
    parser.add_argument('--state', type=Path, default=Path('ci-manual'))
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    if args.mode == 'prepare':
        return prepare(args.state)
    if args.mode == 'serve':
        return serve(args.state)
    if args.mode == 'wait':
        return wait(args.state, args.timeout)
    if (args.state / 'private-path.json').is_file():
        cleanup(Path(read(args.state / 'private-path.json')['folder']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
