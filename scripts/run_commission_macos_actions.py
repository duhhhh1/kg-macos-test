#!/usr/bin/env python3
"""Run the pinned native macOS kit on GitHub Actions through an SSH tunnel.

This controller uses only the standard library. Delivery code runs with the
Python 3.11 runtime shipped inside the verified kit, on the actual Mac runner.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import socket
import stat
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen
import zipfile

try:
    from .commission_macos_reverse_ssh import ReverseSSH
except ImportError:
    from commission_macos_reverse_ssh import ReverseSSH


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def extract_kit(archive, destination):
    """Validate the whole ZIP before writing any entry or running its code."""
    with zipfile.ZipFile(archive) as bundle:
        seen = set()
        total = 0
        for entry in bundle.infolist():
            name = entry.filename
            relative = PurePosixPath(name)
            mode = entry.external_attr >> 16
            if (not name or '\\' in name or relative.is_absolute() or '..' in relative.parts
                    or ':' in name or stat.S_ISLNK(mode) or str(relative) in seen):
                raise ValueError('Unsafe or duplicate ZIP entry: ' + name)
            seen.add(str(relative))
            total += entry.file_size
        if total > 3 * 1024 ** 3:
            raise ValueError('Unexpected expanded kit size (over 3 GiB).')
        bundle.extractall(destination)
    if not (destination / 'start-macos-test.command').is_file():
        raise ValueError('The archive is not the complete native macOS kit.')


def validate_native(round_folder):
    launcher = json.loads((round_folder / 'launcher-summary.json').read_text(encoding='utf-8-sig'))
    client = json.loads((round_folder / 'native/client-run-summary.json').read_text(encoding='utf-8-sig'))
    evidence = round_folder / 'native/platform-evidence-darwin.json'
    if (launcher.get('actual_system') != 'Darwin' or launcher.get('native_completed') is not True
            or client.get('actual_system') != 'Darwin' or client.get('status') != 'completed'
            or client.get('native_target_satisfied') is not True):
        raise ValueError('A completed native macOS execution is required.')
    if sha(evidence) != client.get('export_sha256') or sha(evidence) != launcher.get('evidence_sha256'):
        raise ValueError('Native report SHA-256 mismatch.')
    report = json.loads(evidence.read_text(encoding='utf-8-sig'))
    if set(report.get('domains', {})) != {'tomato', 'pig', 'fish'}:
        raise ValueError('Evidence must include all three domains.')
    for domain in report['domains'].values():
        env = domain.get('environment', {})
        try:
            mac_major = int(env.get('mac_version', '0').split('.')[0])
        except (ValueError, TypeError):
            mac_major = 0
        if env.get('system') != 'Darwin' or mac_major < 12:
            raise ValueError('Domain environment is not supported native macOS.')
    # The dashboard additionally verifies fingerprints, actual image answers,
    # request bindings, content signatures and the formal model name.
    return report


def json_request(url, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    request = Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=90) as response:
        return json.load(response)


def free_ports():
    sockets = []
    try:
        for _ in range(2):
            item = socket.socket()
            item.bind(('127.0.0.1', 0))
            sockets.append(item)
        return [item.getsockname()[1] for item in sockets]
    finally:
        for item in sockets:
            item.close()


def connection_settings(environ):
    host = environ.get('KG_SSH_HOST', 'tibaiot.7766.org').strip()
    user = environ.get('KG_SSH_USER', 'dujx').strip()
    port = int(environ.get('KG_SSH_PORT', '60005'))
    expected = environ.get('KG_MACOS_KIT_SHA256', '').strip().lower()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', host):
        raise ValueError('KG_SSH_HOST must be a DNS name or IPv4 address.')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', user) or not 1 <= port <= 65535:
        raise ValueError('Invalid SSH user or port.')
    if not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise ValueError('Set KG_MACOS_KIT_SHA256 to the trusted complete-kit SHA-256.')
    return host, user, port, expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('ci-results'))
    parser.add_argument('--ssh-only', action='store_true', help='Verify both SSH directions without executing project tests.')
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {'schema': 'commission-macos-actions-v1', 'started_at': datetime.now(timezone.utc).isoformat(),
               'status': 'failed', 'native_completed': False, 'dashboard_imported': False}
    tunnel = None
    native = None
    kit = None
    ssh_log = None
    work = None
    reverse = None
    dashboard = None
    connected_to_workbench = False
    github_run_id = os.environ.get('GITHUB_RUN_ID', '')
    repository = os.environ.get('GITHUB_REPOSITORY', 'duhhhh1/kg-macos-test')
    reverse_port = 32315
    exit_code = 1

    def progress(status):
        summary['stage'] = status
        if dashboard and github_run_id.isdecimal():
            try:
                json_request(dashboard + '/api/platform-macos-job',
                             {**summary, 'repository': repository, 'github_run_id': github_run_id, 'status': status})
            except Exception:
                print('Progress update unavailable; local records are retained.', flush=True)
    # Remove secrets before launching any delivery process. They only ever live
    # in a private temporary directory, outside the uploaded results directory.
    identity = os.environ.pop('KG_CI_SSH_KEY', '')
    known_hosts = os.environ.pop('KG_CI_SSH_KNOWN_HOSTS', '')
    try:
        environment = {'actual_system': platform.system(), 'mac_version': platform.mac_ver()[0],
                       'architecture': platform.machine(), 'controller_python': platform.python_version()}
        for name in ('ImageOS', 'ImageVersion', 'RUNNER_OS', 'RUNNER_ARCH', 'RUNNER_NAME',
                     'GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'GITHUB_SHA'):
            environment[name] = os.environ.get(name, '')
        save(output / 'ci-environment.json', environment)
        if platform.system() != 'Darwin':
            raise ValueError('Run this workflow on a macOS GitHub-hosted runner; Linux cannot supply macOS evidence.')
        host, user, port, expected = connection_settings(os.environ)
        if not identity.strip() or not known_hosts.strip():
            raise ValueError('Configure KG_CI_SSH_KEY and KG_CI_SSH_KNOWN_HOSTS in GitHub Actions secrets.')
        work = Path(tempfile.mkdtemp(prefix='kg-macos-actions-'))
        key = work / 'identity'
        key.write_text(identity.strip() + '\n', encoding='utf-8')
        key.chmod(0o600)
        identity = ''
        known = work / 'known_hosts'
        known.write_text(known_hosts.strip() + '\n', encoding='utf-8')
        known.chmod(0o600)
        known_hosts = ''
        controller_public = Path(__file__).with_name('macos-controller-public-key.pub')
        reverse = ReverseSSH(work, output)
        reverse.start(controller_public.read_text(encoding='utf-8').strip())
        web_port, model_port = free_ports()
        dashboard = f'http://127.0.0.1:{web_port}'
        endpoint = f'http://127.0.0.1:{model_port}/v1/chat/completions'
        summary.update(ssh_target=f'{user}@{host}:{port}', dashboard_url=dashboard,
                       endpoint=endpoint, expected_kit_sha256=expected)
        command = ['ssh', '-F', '/dev/null', '-N', '-T', '-i', str(key), '-p', str(port),
                   '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=20',
                   '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={known}',
                   '-o', 'ServerAliveInterval=20', '-o', 'ServerAliveCountMax=3',
                   '-o', 'ExitOnForwardFailure=yes',
                   '-L', f'127.0.0.1:{web_port}:127.0.0.1:18765',
                   '-L', f'127.0.0.1:{model_port}:127.0.0.1:18100',
                   '-R', f'127.0.0.1:{reverse_port}:127.0.0.1:{reverse.port}', f'{user}@{host}']
        ssh_log = (output / 'ssh.log').open('w', encoding='utf-8')
        tunnel = subprocess.Popen(command, stdout=ssh_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 60
        while True:
            if tunnel.poll() is not None:
                raise RuntimeError('SSH tunnel exited. See ssh.log (key, pinned host, forwarding or network).')
            try:
                info = json_request(dashboard + '/api/connection-info')
                if info.get('service') != 'kg-commission-workbench':
                    raise ValueError('Forwarded server is not the expected workbench.')
                break
            except (OSError, ValueError):
                if time.monotonic() > deadline:
                    raise RuntimeError('Workbench is unreachable through SSH. See ssh.log.')
                time.sleep(1)
        save(output / 'workbench-connection.json', info)
        connected_to_workbench = True
        progress('ssh_check')
        connectivity = json_request(dashboard + '/api/macos-ssh-probe',
                                    reverse.request(github_run_id, repository, reverse_port))
        if (connectivity.get('status') != 'passed' or connectivity.get('mac_to_linux') is not True
                or connectivity.get('linux_to_mac') is not True or connectivity.get('actual_system') != 'Darwin'):
            raise ValueError('Both SSH directions must pass on the actual Mac before project execution.')
        save(output / 'ssh-connectivity.json', connectivity)
        summary['connectivity'] = connectivity
        summary.update(actual_system=environment['actual_system'], mac_version=environment['mac_version'],
                       architecture=environment['architecture'])
        progress('ssh_verified')
        print('Mac → Linux and Linux → Mac SSH verification passed.', flush=True)
        if args.ssh_only:
            summary['status'] = 'ssh_only_completed'
            exit_code = 0
            progress('ssh_only_completed')
            return 0
        progress('downloading')
        metadata = json_request(dashboard + '/api/macos-kit')
        save(output / 'download-metadata.json', metadata)
        if not metadata.get('available') or metadata.get('sha256') != expected:
            raise ValueError('Server kit metadata does not match KG_MACOS_KIT_SHA256.')
        archive = work / 'kg-commission-macos.zip'
        print('Downloading the pinned complete macOS kit through SSH...', flush=True)
        with urlopen(dashboard + '/api/macos-kit-download', timeout=600) as source, archive.open('wb') as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
        if sha(archive) != expected or archive.stat().st_size != metadata.get('size'):
            raise ValueError('Downloaded macOS kit SHA-256 or size mismatch.')
        kit = work / 'kit'
        extract_kit(archive, kit)
        # Put native output in the artifact directory from the first write, so
        # logs already exist there even if Actions interrupts a long model call.
        (output / 'macos-results').mkdir()
        (kit / 'macos-results').symlink_to(output / 'macos-results', target_is_directory=True)
        print('Executing all three domains on native macOS; inference uses the server model.', flush=True)
        progress('running')
        with (output / 'native-console.log').open('w', encoding='utf-8') as log:
            native = subprocess.Popen(['bash', str(kit / 'start-macos-test.command'),
                                       '--dashboard-url', dashboard, '--endpoint', endpoint, '--skip-import'],
                                      cwd=kit, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding='utf-8', errors='replace')
            try:
                for line in native.stdout:
                    # Detailed project output stays in the private result bundle
                    # sent to the existing website, outside public Actions logs.
                    log.write(line)
                    log.flush()
                code = native.wait()
            finally:
                native.stdout.close()
            if code:
                raise RuntimeError(f'Native macOS tests exited {code}. Results and failed logs are preserved.')
        rounds = sorted((kit / 'macos-results').glob('*'))
        if len(rounds) != 1:
            raise ValueError('Expected exactly one native test round in the fresh kit.')
        report = validate_native(rounds[0])
        summary.update(native_completed=True, evidence_sha256=sha(rounds[0] / 'native/platform-evidence-darwin.json'))
        progress('collecting')
        # Return the actual native logs with the report. The existing website can
        # then show original retrievals/calls and offer the complete result ZIP.
        results_zip = work / 'native-results.zip'
        with zipfile.ZipFile(results_zip, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted((output / 'macos-results').rglob('*')):
                if path.is_file():
                    bundle.write(path, path.relative_to(output).as_posix())
            for name in ('ci-environment.json', 'download-metadata.json', 'native-console.log', 'ssh-connectivity.json'):
                bundle.write(output / name, name)
        request = Request(dashboard + '/api/platform-evidence-upload', data=results_zip.read_bytes(),
                          headers={'Content-Type': 'application/zip'})
        with urlopen(request, timeout=180) as response:
            imported = json.load(response)
        save(output / 'dashboard-import.json', imported)
        summary.update(dashboard_imported=True, import_run=imported['id'], status='completed')
        progress('completed')
        print('Native macOS evidence imported: ' + imported['id'], flush=True)
        exit_code = 0
    except Exception as error:
        summary['error'] = str(error)
        print('TEST STOPPED: ' + str(error), flush=True)
        progress('failed')
    finally:
        if native is not None and native.poll() is None:
            native.terminate()
            try:
                native.wait(timeout=10)
            except subprocess.TimeoutExpired:
                native.kill()
                native.wait()
        summary.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=exit_code)
        save(output / 'ci-summary.json', summary)
        if connected_to_workbench and not summary['dashboard_imported'] and tunnel.poll() is None:
            try:
                debug_zip = work / 'job-results.zip'
                with zipfile.ZipFile(debug_zip, 'w', zipfile.ZIP_DEFLATED) as bundle:
                    for path in sorted(output.rglob('*')):
                        if path.is_file():
                            bundle.write(path, path.relative_to(output).as_posix())
                request = Request(dashboard + '/api/platform-macos-job-logs', data=debug_zip.read_bytes(),
                                  headers={'Content-Type': 'application/zip'})
                with urlopen(request, timeout=120) as response:
                    json.load(response)
            except Exception:
                print('Detailed log return unavailable; the public status summary remains available.', flush=True)
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait()
        if ssh_log is not None:
            ssh_log.close()
        if reverse is not None:
            reverse.close()
        if work is not None:
            shutil.rmtree(work)
        summary.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=exit_code)
        save(output / 'ci-summary.json', summary)
        # Public repositories publish a small status artifact. Full questions,
        # images, answers and native logs are returned only to the workbench.
        public = {k: summary.get(k) for k in ('schema', 'status', 'stage', 'actual_system', 'mac_version',
                                            'architecture', 'native_completed', 'dashboard_imported',
                                            'started_at', 'finished_at', 'exit_code')}
        public['ssh_bidirectional_passed'] = summary.get('connectivity', {}).get('status') == 'passed'
        public['phase'] = 'ssh-only' if args.ssh_only else 'full-tests'
        if not connected_to_workbench and (output / 'ssh.log').is_file():
            public['connection_failure_detail'] = (output / 'ssh.log').read_text(encoding='utf-8', errors='replace')[-3000:]
        save(output.parent / 'ci-public/summary.json', public)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
