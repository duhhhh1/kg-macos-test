#!/usr/bin/env python3
"""Use normal macOS accessibility controls for one HIT aTrust login attempt."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import time

try:
    from . import inspect_commission_atrust as inspection
    from . import run_commission_macos_actions as native
except ImportError:
    import inspect_commission_atrust as inspection
    import run_commission_macos_actions as native

JXA = r'''
ObjC.import('stdlib');
var se = Application('System Events');
var p = se.processes.byName('aTrust');
p.frontmost = true;
function prop(e,n) {try {return String(e[n]());} catch(x) {return '';}}
function attr(e,n) {try {return String(e.attributes.byName(n).value());} catch(x) {return '';}}
function items() {return p.windows[0].entireContents();}
function fields(es) {return es.filter(function(e){return prop(e,'role')==='AXTextField';});}
function secure(e) {return /secure/i.test(prop(e,'subrole')+' '+attr(e,'AXSubrole'));}
function hint(e) {return [prop(e,'description'),prop(e,'name'),attr(e,'AXPlaceholderValue')].join(' ');}
function clickLabel(es,rx) {
 var matches=es.filter(function(e){var r=prop(e,'role');return (r==='AXStaticText'||r==='AXButton')&&rx.test(prop(e,'name')||prop(e,'value'));});
 if (!matches.length) return false;
 se.click(matches[matches.length-1]);return true;
}
function typeIn(e,text) {e.focused=true;se.keystroke('a',{using:['command down']});se.keystroke(text);}
var mode=String($.getenv('KG_ATRUST_UI_MODE'));
var es=items(),fs=fields(es),pw=fs.filter(secure);
if(mode==='connect') {
 if(fs.length!==1||pw.length) throw Error('Expected the initial one-field server address page');
 typeIn(fs[0],'https://ivpn.hit.edu.cn');
 if(!clickLabel(es,/^OK$|^确定$|^连接$/i)) se.keyCode(36);
 JSON.stringify({connected_form_submitted:true});
} else if(mode==='inspect') {
 var hints=fs.map(function(e){return {secure:secure(e),hint:hint(e),role:prop(e,'role'),subrole:prop(e,'subrole')};});
 var text=es.filter(function(e){return prop(e,'role')==='AXStaticText';}).map(function(e){return prop(e,'name')||prop(e,'value');}).join(' ');
 JSON.stringify({fields:hints,form_text:text,has_password:pw.length>0,challenge:fs.some(function(e){return /captcha|verification code|验证码|动态码|短信/i.test(hint(e));}),
                 account_tab:/Account login|账号登录|帐户登录/.test(text),
                 login_rejected:/密码错误|账号或密码|用户名或密码|incorrect password|invalid credentials/i.test(text)});
} else if(mode==='account-tab') {
 JSON.stringify({clicked:clickLabel(es,/^Account login$|^账号登录$|^帐户登录$/i)});
} else if(mode==='login') {
 var usernames=fs.filter(function(e){return !secure(e)&&/student|work ID|username|account|学号|工号|用户名|账号/i.test(hint(e));});
 if(!usernames.length) usernames=fs.filter(function(e){return !secure(e)&&!/captcha|verification|验证码|动态码|短信/i.test(hint(e));});
 if(usernames.length!==1||pw.length!==1) throw Error('Cannot uniquely identify the account/password fields');
 if(fs.some(function(e){return /captcha|verification code|验证码|动态码|短信/i.test(hint(e));})) throw Error('Interactive verification is required');
 typeIn(usernames[0],String($.getenv('HIT_VPN_USERNAME')));
 typeIn(pw[0],String($.getenv('HIT_VPN_PASSWORD')));
 if(!clickLabel(items(),/^Login$|^登录$/i)) se.keyCode(36);
 JSON.stringify({login_submitted:true});
}
'''


def ui(mode, username=None, password=None):
    env = {**os.environ, 'KG_ATRUST_UI_MODE': mode}
    if username is not None:
        env['HIT_VPN_USERNAME'] = username
        env['HIT_VPN_PASSWORD'] = password
    result = subprocess.run(['osascript', '-l', 'JavaScript', '-e', JXA], env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        # Do not publish UI values or native automation exception dumps.
        raise RuntimeError('The normal aTrust UI could not complete stage: ' + mode)
    return json.loads(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-only', action='store_true')
    args = parser.parse_args()
    username = os.environ.pop('HIT_VPN_USERNAME', '').strip()
    password = os.environ.pop('HIT_VPN_PASSWORD', '')
    folder = Path('ci-public')
    summary = {'schema': 'commission-macos-actions-v1', 'phase': 'atrust-login',
               'status': 'failed', 'stage': 'atrust_install', 'native_completed': False,
               'dashboard_imported': False, 'credentials_used': False,
               'started_at': datetime.now(timezone.utc).isoformat()}
    handed_to_native = False
    try:
        if not username or not password:
            raise ValueError('Configure the two HIT_VPN repository Secrets for the authorized account.')
        if inspection.main(['--output', str(folder)]):
            raise RuntimeError('University client installation/start inspection did not pass.')
        installed = json.loads((folder / 'summary.json').read_text())
        for key in ('actual_system', 'mac_version', 'architecture', 'client_installed', 'client_started'):
            summary[key] = installed.get(key)
        if installed.get('ui_automation_enabled') is not True:
            raise RuntimeError('This Mac requires interactive accessibility approval before login.')
        summary['stage'] = 'atrust_server_address'
        ui('connect')
        print('University gateway submitted through the normal client UI.', flush=True)
        deadline = time.monotonic() + 100
        tab_clicked = False
        while time.monotonic() < deadline:
            view = ui('inspect')
            # This snapshot is taken only before any credentials are entered.
            inspection.save(folder, 'prelogin-state.json', view)
            if view.get('challenge'):
                raise RuntimeError('School login requires an interactive verification code; account credentials were not submitted.')
            if view.get('has_password'):
                break
            if view.get('account_tab') and not tab_clicked:
                ui('account-tab')
                tab_clicked = True
            time.sleep(2)
        else:
            inspection.run(['screencapture', '-x', str(folder / 'client-gateway-before-login.png')])
            raise RuntimeError('The school account/password form did not become available in this client.')
        summary['stage'] = 'atrust_account_login'
        ui('login', username, password)
        summary['credentials_used'] = True
        username = password = ''
        print('One authorized login submitted; waiting for campus SSH connectivity.', flush=True)
        host = os.environ.get('KG_SSH_HOST', 'tibaiot.7766.org')
        port = int(os.environ.get('KG_SSH_PORT', '60005'))
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=3) as connection:
                    connection.settimeout(3)
                    if connection.recv(120).startswith(b'SSH-'):
                        summary['campus_ssh_reachable'] = True
                        break
            except OSError:
                pass
            view = ui('inspect')
            if view.get('challenge'):
                raise RuntimeError('School login requires interactive second-factor verification.')
            if view.get('login_rejected'):
                raise RuntimeError('The school rejected the single account login attempt; no retry was made.')
            time.sleep(3)
        else:
            raise RuntimeError('Campus SSH was not reachable after the login attempt; no project pass was recorded.')
        summary.update(status='atrust_campus_connected', stage='campus_ssh_reachable')
        inspection.save(folder, 'campus-connection.json', summary)
        print('Campus SSH is reachable. Verifying both SSH directions before project execution.', flush=True)
        handed_to_native = True
        return native.main(['--output', 'ci-results'] + (['--ssh-only'] if args.ssh_only else []))
    except Exception as error:
        summary['error'] = str(error)
        print('aTrust login stopped: ' + str(error), flush=True)
        return 1
    finally:
        username = password = ''
        if not handed_to_native:
            folder.mkdir(exist_ok=True)
            summary.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=1)
            inspection.save(folder, 'summary.json', summary)


if __name__ == '__main__':
    raise SystemExit(main())
