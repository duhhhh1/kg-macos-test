# Tailscale：校园网服务器与 GitHub macOS 原生测试接入

当前服务器在校园网内。`tibaiot.7766.org` 在本次 DNS 查询中解析为 `10.160.22.90`，属于私网地址。真实 GitHub macOS 15 任务 `40175179133` 连接该地址的60005端口超时，未进入项目测试。

Tailscale 为服务器与临时 Mac 建立一个由你管理的私有网络。两端通过互联网主动建立连接，能直连时直连，不能直连时尝试 DERP 中继。实际可用性仍以两端登录、节点连通和 SSH 实测为准。

## 连接结构

```text
GitHub 标准 macos-15 runner（临时 Tailscale 节点，tag:kg-ci）
  → 服务器 Tailscale IPv4:2222
  → 本机 SSH 127.0.0.1:22（原生 OpenSSH 与专用 CI 密钥）
  → SSH 本地转发：网页18765、模型18100
  → SSH 反向转发：Linux 32315 → 本轮 Mac 临时 sshd
```

服务器使用 Tailscale 用户模式，不要求 dujx 具备免密 sudo。TCP2222只在Tailnet提供到本机SSH的转发；没有配置子网路由、出口节点或Funnel。Windows上已有的VS Code网页转发继续可用。加入同一Tailnet的Windows/Mac也可通过普通SSH隧道访问网页。

## 第一步：将服务器加入你的 Tailnet

Tailscale 1.104.2 已按官方静态包安装在：

```text
/home/dujx/.local/share/kg-commission-tailscale/
```

二进制已按官方发布的SHA-256校验，安装记录在该目录 `install-verification.json`。节点私有状态在 `/home/dujx/.local/state/kg-commission-tailscale/`，目录权限700，不能提交到GitHub。

在VS Code连接服务器后的远程终端执行：

```bash
cd /mnt/disk2/dujx/kg_demo
.venv/bin/python -B scripts/commission_tailscale_server.py login
```

打开终端输出的 `https://login.tailscale.com/...` 地址，在Tailscale官方网站登录你自己的账号，确认加入设备 **kg-commission-server**。如果管理后台要求设备审批，完成审批后再继续。不要把密码、验证码或设备登录链接提交到仓库。

查询状态：

```bash
.venv/bin/python -B scripts/commission_tailscale_server.py status
```

应出现 `state: Running` 和服务器实际的 `100.x.y.z` IPv4。

## 第二步：创建允许 Mac CI 加入同一 Tailnet 的凭据

1. 打开 https://login.tailscale.com/admin/acls ，在现有网络策略中声明 `tag:kg-ci`。例如在现有 `tagOwners` 对象增加：

   ```json
   "tag:kg-ci": ["autogroup:admin"]
   ```

2. 如果现有网络策略不允许该CI节点访问服务器，在现有 `grants` 列表增加本项目规则，将示例IP替换成服务器第一步取得的真实Tailscale地址：

   ```json
   {
     "src": ["tag:kg-ci"],
     "dst": ["100.x.y.z"],
     "ip": ["tcp:2222"]
   }
   ```

   这是现有策略的增量示例，保留其他有效规则。Tailscale访问规则是累加的；如果现有策略已有全网允许规则，增加本条不会自动收窄那条规则。

3. 打开 https://login.tailscale.com/admin/settings/oauth ，创建本项目专用OAuth客户端。允许写入 **Auth Keys**（`auth_keys` write），关联 **tag:kg-ci**，记下 Client ID 和 Client secret。
4. 打开 https://github.com/duhhhh1/kg-macos-test/settings/secrets/actions ，创建两个Repository Secrets：

   | 名称 | 内容 |
   | --- | --- |
   | `TS_OAUTH_CLIENT_ID` | 刚创建的Tailscale OAuth Client ID |
   | `TS_OAUTH_SECRET` | 刚创建的Tailscale OAuth Client secret |

5. 原来的 `KG_CI_SSH_KEY` 和 `KG_CI_SSH_KNOWN_HOSTS` 仍用于SSH身份及主机公钥验证。Tailscale OAuth只负责节点加入私有网络，不能替代这两项SSH校验。

也可在自己的服务器终端通过 `gh secret set 名称 --repo duhhhh1/kg-macos-test` 交互输入；不要将Secret值作为命令行参数或发送到聊天。

## 第三步：设置私有 SSH 入口并更新 GitHub 变量

服务器状态为Running后执行：

```bash
.venv/bin/python -B scripts/commission_tailscale_server.py configure --github
```

它会完成：

- Tailscale Serve TCP2222 → 本机127.0.0.1:22，仅在Tailnet访问。
- GitHub Variable `KG_USE_TAILSCALE=true`。
- `KG_SSH_HOST` 改为服务器实际的100.x地址，`KG_SSH_PORT=2222`、`KG_SSH_USER=dujx`。
- 从当前服务器可信的 `/etc/ssh/ssh_host_ed25519_key.pub` 生成新入口的known_hosts条目，直接更新 `KG_CI_SSH_KNOWN_HOSTS` Secret。

本次脚本只操作项目自己的用户模式Tailscale服务和上述仓库配置，不要求修改系统SSH配置。

服务器重启后需要先运行 `scripts/commission_tailscale_server.py start` 恢复用户模式进程，再检查status和serve状态。登录状态保存在私有state目录；节点密钥过期时需重新认证。

## 第四步：先连接验证，再正式执行

1. 在 https://github.com/duhhhh1/kg-macos-test/actions 点击 **macOS native commission tests → Run workflow**。
2. 选择 **ssh-only**。工作流先通过官方Tailscale Action加入同一Tailnet，以临时节点tag:kg-ci运行，并等待服务器连通。
3. 然后执行原来的Mac→Linux及Linux→Mac反向SSH挑战验证。
4. 只有双向通过后，才运行第二轮 **full-tests**。
5. 正式轮再次验证双向SSH，下载固定SHA-256的完整Mac运行包，在真实Mac上执行三领域代码、图谱、检索和9条图文预测，然后自动回传原生结果及日志。
6. 在原网站 **平台实验与问答 → macOS原生实验** 查看结果，之后与Windows原生记录完成跨平台对照。

Tailscale Action固定到v4提交 `99a8333667fff04fdd6cffb46dfd409f8329a7bf`，客户端固定1.104.2，关闭Action缓存。临时CI节点在任务结束时登出并回收。运行包和完整答卷不提交到公开仓库。

## 网站如何查看连接失败及原生结果

原网站会通过服务器已配置的GitHub CLI认证，约每45秒读取本仓库的运行状态。即使校园网SSH尚未连接，GitHub中的状态摘要和公开执行日志也能回收到本地，在 **平台实验与问答 → 日志与结果导入 → SSH执行与自动回收** 查看或下载。

这种状态同步不会授予兼容性通过。只有完成实际原生项目执行、输入输出及软件指纹校验，并通过原生结果导入后，才更新macOS兼容性；跨平台一致性继续按实际对照复核。

## 常见状态

| 状态 | 检查方法 |
| --- | --- |
| NeedsLogin | 完成第一步设备登录；链接失效时重新运行login |
| NeedsMachineAuth | 在Tailnet管理后台审批服务器节点 |
| Tailscale节点加入失败 | 检查两个TS_OAUTH Secrets、Auth Keys写权限与tag:kg-ci授权 |
| tailscale ping失败 | 确认服务器进程在线、两端是同一Tailnet、设备已审批，检查出站网络是否允许协调服务及DERP |
| Tailscale已连通但2222超时 | 检查serve配置及Tailnet访问规则 |
| Host key verification failed | 重新运行configure --github，固定当前可信服务器SSH主机公钥 |
| Permission denied (publickey) | 检查KG_CI_SSH_KEY和当前Linux用户的专用公钥授权 |
| 双向SSH通过但项目失败 | 在网页查看原生执行日志；修复实际错误后重跑，保留失败轮次 |

官方资料：

- https://github.com/tailscale/github-action
- https://tailscale.com/kb/1112/userspace-networking
- https://tailscale.com/kb/1242/tailscale-serve
- https://tailscale.com/kb/1215/oauth-clients

GitHub公开仓库标准macos-15运行时长的免费条件与Tailscale账户套餐分别适用。Tailscale账户的用户/设备数量和功能以你的实际套餐及官方当前政策为准。
