#!/usr/bin/env python3
"""Check the university-supplied aTrust client on an actual Mac, without login."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import plistlib
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

URL = 'https://ivpn.hit.edu.cn/resource/client/mac/aTrustInstaller.pkg'
SHA256 = 'd8f6866aac9407edf348fca1fd890d44fc6c63a1aea4bf92184f1d30a23b719d'
SIZE = 234726127


def run(command, timeout=60):
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=timeout)
    return {'returncode': result.returncode, 'output': (result.stdout + result.stderr)[-8000:]}


def save(folder, name, value):
    (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('ci-public'))
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {'schema': 'commission-macos-actions-v1', 'phase': 'atrust-preflight',
               'started_at': datetime.now(timezone.utc).isoformat(), 'status': 'failed',
               'actual_system': platform.system(), 'mac_version': platform.mac_ver()[0],
               'architecture': platform.machine(), 'native_completed': False, 'dashboard_imported': False,
               'ssh_bidirectional_passed': False, 'credentials_used': False,
               'scope': 'Client installation/start inspection only; no account login or project test.'}
    details = {'package_url': URL, 'expected_sha256': SHA256, 'expected_size': SIZE}
    exit_code = 1
    try:
        if platform.system() != 'Darwin':
            raise ValueError('This inspection requires actual macOS.')
        summary['stage'] = 'atrust_download'
        print('Downloading and checking the university macOS client...', flush=True)
        with tempfile.TemporaryDirectory(prefix='kg-atrust-inspect-') as temporary:
            package = Path(temporary) / 'aTrustInstaller.pkg'
            digest = hashlib.sha256()
            with urlopen(Request(URL, headers={'User-Agent': 'kg-commission-macos-preflight'}), timeout=120) as src, package.open('wb') as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    dst.write(chunk)
            details.update(actual_size=package.stat().st_size, actual_sha256=digest.hexdigest())
            if details['actual_size'] != SIZE or details['actual_sha256'] != SHA256:
                raise ValueError('University client package size or SHA256 changed; inspect before installing.')
            details['package_signature'] = run(['pkgutil', '--check-signature', str(package)])
            if (details['package_signature']['returncode'] != 0
                    or 'SANGFOR' not in details['package_signature']['output']):
                raise ValueError('Expected valid SANGFOR installer signature.')
            summary['stage'] = 'atrust_install'
            print('Signature verified; installing the university client...', flush=True)
            details['installer'] = run(['sudo', '-n', 'installer', '-pkg', str(package), '-target', '/'], timeout=900)
            if details['installer']['returncode']:
                raise RuntimeError('Native macOS installer failed; see client-layout.json.')
        app = Path('/Applications/aTrust.app')
        if not app.is_dir():
            raise ValueError('Installer did not create /Applications/aTrust.app.')
        with (app / 'Contents/Info.plist').open('rb') as source:
            info = plistlib.load(source)
        details['app'] = {key: info.get(key) for key in ('CFBundleIdentifier', 'CFBundleExecutable',
                                                        'CFBundleVersion', 'CFBundleShortVersionString')}
        executable = app / 'Contents/MacOS' / info['CFBundleExecutable']
        details['architecture'] = run(['file', str(executable)])
        details['app_signature'] = run(['codesign', '-dv', '--verbose=2', str(app)])
        summary['stage'] = 'atrust_start'
        print('Installation completed; checking normal launch and UI availability...', flush=True)
        details['launch'] = run(['open', '-a', str(app)])
        time.sleep(3)
        details['ui_automation'] = run(['osascript', '-e',
                                        'tell application "System Events" to get UI elements enabled'])
        details['ui_windows'] = run(['osascript', '-e',
                                    'tell application "System Events" to tell process "aTrust" to get name of every window'])
        if details['ui_automation']['output'].strip() == 'true' and details['ui_windows']['returncode'] == 0:
            details['ui_accessibility'] = run(['osascript', '-e',
                                               'tell application "System Events" to tell process "aTrust" to set value of attribute "AXEnhancedUserInterface" to true'])
            details['ui_manual_accessibility'] = run(['osascript', '-e',
                                                      'tell application "System Events" to tell process "aTrust" to set value of attribute "AXManualAccessibility" to true'])
            time.sleep(5)
            details['ui_controls'] = run(['osascript', '-e',
                                         'tell application "System Events" to tell process "aTrust" to get entire contents of window 1'])
            details['ui_screenshot'] = run(['screencapture', '-x', str(output / 'client-before-login.png')])
        tools = Path('/Library/sangfor/SDP/aTrust.app/Contents/Resources/bin/aTrustClientTools')
        if tools.is_file():
            details['client_tools_help'] = run([str(tools), '--help'], timeout=15)
        process = run(['pgrep', '-fl', 'aTrust'])
        details['processes'] = process
        details['system_extensions'] = run(['systemextensionsctl', 'list'])
        installed = Path('/Library/sangfor/SDP')
        details['native_components'] = [str(path) for path in installed.rglob('*')
                                        if path.is_file() and path.name in ('Info.plist', 'aTrustCore', 'aTrustTunnel',
                                                                          'aTrustDaemon', 'aTrust', 'sfclient', 'atrust-cli')][:80]
        if details['launch']['returncode'] or process['returncode']:
            raise ValueError('Installed client did not start on this Mac.')
        summary.update(status='atrust_preflight_completed', stage='atrust_installed',
                       client_installed=True, client_started=True,
                       ui_automation_enabled=details['ui_automation']['output'].strip() == 'true')
        exit_code = 0
        print('aTrust installed and started on actual macOS; no credentials used.', flush=True)
    except Exception as error:
        summary['error'] = str(error)
        print('aTrust preflight stopped: ' + str(error), flush=True)
    finally:
        summary.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=exit_code)
        save(output, 'client-layout.json', details)
        save(output, 'summary.json', summary)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
