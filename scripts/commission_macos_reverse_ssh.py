"""Ephemeral loopback-only SSH listener for Linux-to-Mac connectivity checks."""
import getpass
import json
from pathlib import Path
import platform
import shlex
import socket
import subprocess
import sys
import time
import uuid


class ReverseSSH:
    def __init__(self, work, output):
        self.work = Path(work)
        self.output = Path(output)
        self.process = None
        self.log = None
        self.user = getpass.getuser()
        self.nonce = uuid.uuid4().hex

    def start(self, public_key):
        if platform.system() != 'Darwin':
            raise ValueError('The reverse SSH listener must run on actual macOS.')
        import re
        if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]{40,200}(?: [^\r\n]{0,180})?', public_key.strip()):
            raise ValueError('Missing or invalid dedicated Linux controller public key.')
        host_key = self.work / 'mac-host-key'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(host_key)], check=True)
        authorized = self.work / 'mac-authorized-keys'
        authorized.write_text('restrict ' + public_key.strip() + '\n', encoding='utf-8')
        authorized.chmod(0o600)
        probe = self.work / 'mac-probe.py'
        probe.write_text('import json,platform\nprint(json.dumps({"actual_system":platform.system(),'
                         '"mac_version":platform.mac_ver()[0],"architecture":platform.machine(),'
                         f'"nonce":{self.nonce!r}' + '}))\n', encoding='utf-8')
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            self.port = listener.getsockname()[1]
        config = self.work / 'mac-sshd-config'
        config.write_text('\n'.join([
            f'Port {self.port}', 'ListenAddress 127.0.0.1', f'HostKey {host_key}',
            f'PidFile {self.work / "mac-sshd.pid"}', f'AuthorizedKeysFile {authorized}',
            'PasswordAuthentication no', 'KbdInteractiveAuthentication no', 'PubkeyAuthentication yes',
            'UsePAM no', 'StrictModes yes', 'PermitRootLogin no', f'AllowUsers {self.user}',
            'AllowTcpForwarding no', 'AllowAgentForwarding no', 'X11Forwarding no',
            'PermitTTY no', 'PermitUserEnvironment no', 'LogLevel VERBOSE',
            'ForceCommand ' + shlex.join([sys.executable, str(probe)]), '']), encoding='utf-8')
        self.log = (self.output / 'mac-sshd.log').open('w', encoding='utf-8')
        self.process = subprocess.Popen(['sudo', '-n', '/usr/sbin/sshd', '-D', '-e', '-f', str(config)],
                                        stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 10
        while True:
            if self.process.poll() is not None:
                raise RuntimeError('Temporary Mac SSH listener exited; see mac-sshd.log.')
            try:
                with socket.create_connection(('127.0.0.1', self.port), timeout=1):
                    break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError('Temporary Mac SSH listener did not start.')
                time.sleep(.2)
        return self

    def request(self, run_id, repository, reverse_port):
        return {'github_run_id': run_id, 'repository': repository, 'reverse_port': reverse_port,
                'ssh_user': self.user, 'nonce': self.nonce,
                'host_public_key': (self.work / 'mac-host-key.pub').read_text().strip()}

    def close(self):
        if self.process is not None and self.process.poll() is None:
            # Root-owned sshd is a task-specific process; stop only this listener.
            pidfile = self.work / 'mac-sshd.pid'
            if pidfile.is_file():
                pid = pidfile.read_text().strip()
                if pid.isdecimal():
                    subprocess.run(['sudo', '-n', 'kill', '-TERM', pid], capture_output=True)
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                subprocess.run(['sudo', '-n', 'kill', '-TERM', str(self.process.pid)], capture_output=True)
        if self.log is not None:
            self.log.close()
