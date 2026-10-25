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
var mode=String($.getenv('KG_ATRUST_UI_MODE'));
var page=null;
function schoolBrowser() {
 try {
  var sp=se.processes.byName('Safari');if(!sp.exists()||!sp.windows().length)return null;
  sp.frontmost=true;
  se.keystroke('l',{using:['command down']});delay(0.2);
  var all=sp.windows[0].entireContents();
  var addresses=all.filter(function(e){return prop(e,'role')==='AXTextField'&&/^https?:\/\//i.test(prop(e,'value'));});
  if(addresses.length!==1){se.keyCode(53);return null;}
  var url=prop(addresses[0],'value');
  se.keyCode(53);
  var match=url.match(/^(https?):\/\/([^\/:?#]+)(?::\d+)?(\/[^?#]*)?/i);
  if(!match||!/(^|\.)hit\.edu\.cn$/i.test(match[2]))return null;
  return {address:addresses[0],url:url,origin:match[1]+'://'+match[2],secure:match[1].toLowerCase()==='https'};
 }catch(x){return null;}
}
if(['inspect','login','upgrade-https'].indexOf(mode)>=0){
 page=schoolBrowser();if(page)p=se.processes.byName('Safari');
}
p.frontmost = true;
function prop(e,n) {try {return String(e[n]());} catch(x) {return '';}}
function attr(e,n) {try {return String(e.attributes.byName(n).value());} catch(x) {return '';}}
function items() {
 var es=[];p.windows().forEach(function(w){es=es.concat(w.entireContents());});return es;
}
function fields(es) {return es.filter(function(e){return prop(e,'role')==='AXTextField';});}
function secure(e) {return /secure/i.test(prop(e,'subrole')+' '+attr(e,'AXSubrole'));}
function hint(e) {return [prop(e,'description'),prop(e,'name'),attr(e,'AXPlaceholderValue')].join(' ');}
function clickLabel(es,rx) {
 var matches=es.filter(function(e){var r=prop(e,'role'),label=(prop(e,'name')||prop(e,'value')).trim();return (r==='AXStaticText'||r==='AXButton')&&(rx.test(label)||rx.test(label.replace(/\s/g,'')));});
 if (!matches.length) return false;
 se.click(matches[matches.length-1]);return true;
}
function typeIn(e,text) {se.click(e);e.focused=true;se.keystroke('a',{using:['command down']});se.keystroke(text);}
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
                 browser_origin:page?page.origin:null,requires_https:page?!page.secure:false,
                 certificate_warning:/This Connection Is Not Private|此连接非私密|证书无效|证书已过期/i.test(text),
                 theme_update:/theme update is available|主题.*更新/i.test(text),
                 cas_entry:/UIA\s*[–-]\s*CAS/i.test(text)&&!pw.length,
                 account_tab:/Account login|账号登录|帐户登录/.test(text),
                 login_rejected:/密码错误|账号或密码|用户名或密码|incorrect password|invalid credentials/i.test(text)});
} else if(mode==='account-tab') {
 JSON.stringify({clicked:clickLabel(es,/^Account login$|^账号登录$|^帐户登录$/i)});
} else if(mode==='dismiss-theme') {
 if(!clickLabel(es,/^Later$|^稍后$|^以后再说$/i)) throw Error('Theme prompt Later button is unavailable');
 JSON.stringify({dismissed:true});
} else if(mode==='cas-entry') {
 var checks=es.filter(function(e){return prop(e,'role')==='AXCheckBox';});
 if(checks.length===1){if(!/^(1|true)$/.test(prop(checks[0],'value'))) se.click(checks[0]);}
 else if(!clickLabel(es,/^I have read and accept|^我已阅读并(同意|接受)/i)) throw Error('Terms acceptance control is unavailable');
 if(!clickLabel(items(),/^Log In$|^Login$|^登录$/i)) throw Error('Normal CAS login button is unavailable');
 JSON.stringify({cas_opened:true});
} else if(mode==='upgrade-https') {
 if(!page||page.secure)throw Error('Expected an HTTP school page before HTTPS navigation');
 typeIn(page.address,page.url.replace(/^http:/i,'https:'));se.keyCode(36);
 JSON.stringify({https_requested:true});
} else if(mode==='login') {
 if(page&&!page.secure)throw Error('School browser login requires HTTPS');
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
    try:
        result = subprocess.run(['osascript', '-l', 'JavaScript', '-e', JXA], env=env,
                                capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise RuntimeError('The normal macOS UI timed out at stage: ' + mode) from None
    if result.returncode:
        # Do not publish UI values or native automation exception dumps.
        message = 'The normal aTrust UI could not complete stage: ' + mode
        if mode in ('connect', 'dismiss-theme', 'cas-entry', 'account-tab'):
            message += ' (' + result.stderr.strip()[-600:] + ')'
        raise RuntimeError(message)
    return json.loads(result.stdout.strip())


def prelogin_screenshot(folder):
    try:
        inspection.run(['screencapture', '-x', str(folder / 'client-gateway-before-login.png')])
    except (OSError, subprocess.SubprocessError):
        pass  # A diagnostic image must never change the authentication result.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh-only', action='store_true')
    args = parser.parse_args()
    username = os.environ.pop('HIT_VPN_USERNAME', '').strip()
    password = os.environ.pop('HIT_VPN_PASSWORD', '')
    ssh_credentials = {key: os.environ.pop(key, '')
                       for key in ('KG_CI_SSH_KEY', 'KG_CI_SSH_KNOWN_HOSTS')}
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
        cas_opened = False
        https_requested = False
        while time.monotonic() < deadline:
            view = ui('inspect')
            # This snapshot is taken only before any credentials are entered.
            inspection.save(folder, 'prelogin-state.json', view)
            if view.get('certificate_warning'):
                raise RuntimeError('The school browser reported a certificate warning; no credentials were entered.')
            if view.get('requires_https'):
                if https_requested:
                    raise RuntimeError('School browser login did not remain on HTTPS; no credentials were entered.')
                ui('upgrade-https')
                https_requested = True
                time.sleep(3)
                continue
            if view.get('challenge'):
                prelogin_screenshot(folder)
                raise RuntimeError('School login requires an interactive verification code; account credentials were not submitted.')
            if view.get('theme_update'):
                ui('dismiss-theme')
                time.sleep(2)
                continue
            if view.get('has_password'):
                break
            if view.get('cas_entry') and not cas_opened:
                ui('cas-entry')
                cas_opened = True
            if view.get('account_tab') and not tab_clicked:
                ui('account-tab')
                tab_clicked = True
            time.sleep(2)
        else:
            prelogin_screenshot(folder)
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
        os.environ.update(ssh_credentials)
        ssh_credentials.clear()
        handed_to_native = True
        return native.main(['--output', 'ci-results'] + (['--ssh-only'] if args.ssh_only else []))
    except Exception as error:
        summary['error'] = str(error)
        if summary['stage'] == 'atrust_server_address':
            # This stage always precedes any account/password entry.
            prelogin_screenshot(folder)
        print('aTrust login stopped: ' + str(error), flush=True)
        return 1
    finally:
        username = password = ''
        ssh_credentials.clear()
        if not handed_to_native:
            folder.mkdir(exist_ok=True)
            summary.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=1)
            inspection.save(folder, 'summary.json', summary)


if __name__ == '__main__':
    raise SystemExit(main())
