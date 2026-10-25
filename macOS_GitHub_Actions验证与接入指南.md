# kg-macos-test：标准 macos-15、双向 SSH 与三领域原生测试

本方案对应仓库 https://github.com/duhhhh1/kg-macos-test ，仓库可见性为 Public。当前网站继续承担讲解、实时问答、实验结果和原始日志查看；GitHub 提供临时 macOS 原生执行环境。

## 2026-10-25实际接入状态

标准macos-15工作流已实际推送并执行，第一轮 `ssh-only` 运行号为 `40175179133`。该轮停在校园网连接阶段：`tibaiot.7766.org`解析为私网 `10.160.22.90`，GitHub连接60005超时，未执行原生项目测试。服务器现在可从GitHub回收本轮状态摘要和执行日志，在原网页查看。

当前按用户选择使用哈工大aTrust直接接入校园网，不要求Mac加入Tailscale。Tailscale只作为可选方案保留，见 [Tailscale校园网接入指南](Tailscale_校园网与GitHub_Mac接入指南.md)。

## 哈工大aTrust直接接入方式

当前用户选择通过学校aTrust接入校园网，GitHub Variable `KG_USE_TAILSCALE` 已设为false，SSH目标恢复为 `dujx@tibaiot.7766.org:60005`。工作流新增 `atrust-preflight`：实际Mac下载学校PKG，校验固定哈希及安装签名，再安装并检查普通启动和UI条件。真实运行40178251763、40178735495已确认客户端可在macOS15.7.9/ARM64安装并启动；账号登录、校园网连通与项目测试继续分别验证。

`atrust-ssh-only`和`atrust-full-tests`从GitHub Secrets取得本人授权的学校账号，通过正常客户端界面尝试一次登录。验证码、二次认证及账号拒绝均停止，不自动重试账号密码。详见 [aTrust校园网接入与验证指南](aTrust_macOS校园网接入与验证指南.md)。公开Artifact只包含状态摘要及提交账号之前的安装/界面诊断；项目答卷与校园网凭据不包含其中。

## 免费使用条件与本次配置

GitHub 官方说明：公开仓库使用标准 GitHub-hosted runners 的运行时长免费。此次工作流固定 `runs-on: macos-15`，使用标准 Apple Silicon runner；没有选择 `-large`、`-xlarge` 等付费大型运行器。

工作流仅由仓库用户手动触发，最长90分钟，同仓库任务串行运行，结束后关闭SSH隧道和本轮临时SSH服务。它用于本知识图谱项目的连接验证和软件测试。Artifact仅保存小型状态摘要，保留7天；完整测试结果回传现有网站。没有开启缓存或付费自定义镜像。

免费范围以GitHub官方当时的政策和账户账单为准，不将标准runner的运行时长免费解释为GitHub所有产品、所有存储或所有运行器都无条件免费。

官方依据：

- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://github.com/actions/runner-images

## 委托要求与实际部署

| 检测项 | 实际验证方法 |
| --- | --- |
| 2CA macOS 12及以上兼容性 | 在macOS 15实际执行同版本三领域代码、schema、Python API、CLI、retrieve与真实图文预测、决策，保存系统、Python、图谱、输入输出和日志 |
| 3CA 跨平台一致性 | 将Mac记录导入当前网站，与已有Windows同版本记录比较核心签名、输入、实体和知识证据，再逐条复核回答的业务含义 |
| Python与依赖 | 完整包内Python 3.11.17和ARM64离线依赖，符合CPython 3.11/3.12及NumPy≥2.1且<3要求 |
| 模型调用 | Mac执行客户端和交付代码；Qwen3-VL-8B-Instruct模型推理由Linux服务器提供 |

报告记录实际macOS版本和ARM64架构。此次运行不证明所有macOS 12以上版本、Intel架构、macOS本机GPU加载模型或Safari人工操作均已验证。

## 本次准备的仓库文件

```text
.github/workflows/commission-macos.yml
scripts/run_commission_macos_actions.py
scripts/commission_macos_reverse_ssh.py
scripts/macos-controller-public-key.pub
scripts/inspect_commission_atrust.py
scripts/login_commission_atrust.py
kit-reference.json
macOS_GitHub_Actions验证与接入指南.md
```

工作流包可以从现有网站 `/native-testing#macos-actions` 下载，解压并保留目录结构放进仓库默认分支。原始交付包约636MiB，通过SSH从现有工作台下载并校验SHA-256；无需提交到公开仓库。

服务器同时保存了一份可提交的仓库副本：`experiments/commission_testing/tools/github/kg-macos-test`。准备文件和本地提交不等于已经推送到GitHub；是否完成发布需查看远端默认分支。

## Secrets：名称和来源

进入仓库 https://github.com/duhhhh1/kg-macos-test/settings/secrets/actions ，选择 **New repository secret**。

| Secret名称 | 内容与来源 |
| --- | --- |
| `KG_CI_SSH_KEY` | 本轮新建的、供Mac runner登录Linux的专用私钥。服务器文件：`/home/dujx/.ssh/kg_commission_github_ci_ed25519`。通过自己的VS Code文件编辑器读取完整内容并粘贴到GitHub Secrets；不要提交到仓库或发送到聊天。对应公钥已加入Linux用户authorized_keys，并限制转发目标为工作台18765、模型18100和反向端口32315。 |
| `KG_CI_SSH_KNOWN_HOSTS` | 已核验的Linux SSH入口主机公钥条目。可从Windows已经验证成功的 `C:\Users\86185\.ssh\known_hosts` 中取得 `[tibaiot.7766.org]:60005` 对应条目。服务器也生成了候选文件 `experiments/commission_testing/tools/macos-actions/ci-server-known-hosts.txt`，按当前Linux主机SSH公钥生成；若公网入口对应其他SSH网关，应使用该入口实际且已核验的公钥。 |
| `HIT_VPN_USERNAME` | aTrust方式需要，本人获授权的学校账号，直接填入GitHub Repository Secrets。 |
| `HIT_VPN_PASSWORD` | aTrust方式需要，与上述账号对应的密码，只填GitHub Secrets；不放进源码、聊天、公开日志或Artifact。 |

本仓库目前已配置以上四个Secrets；只查看运行记录无需再次填写。当前aTrust方式无需配置 `TS_OAUTH_CLIENT_ID` 或 `TS_OAUTH_SECRET`。

主机公钥条目形式：

```text
[tibaiot.7766.org]:60005 ssh-ed25519 <真实主机公钥base64>
```

这里的主机公钥和你登录用的用户公钥用途不同。工作流保留严格主机指纹验证，不使用跳过检查参数。

另一个文件 `scripts/macos-controller-public-key.pub` 是Linux返回登录本轮Mac所需的**公钥**，已随工作流准备，允许放在公开仓库，不需要设为Secret。它对应的私钥 `/home/dujx/.ssh/kg_commission_macos_controller_ed25519` 只留在Linux服务器，不提供给GitHub。

上述两组专用密钥均为本轮新建，不复用此前在聊天中公开过的私钥。

## Variables：默认已经填写，可按实际入口调整

进入 **Settings → Secrets and variables → Actions → Variables**。需要覆盖默认值时添加：

| Variable | 默认值/来源 |
| --- | --- |
| `KG_SSH_HOST` | `tibaiot.7766.org` |
| `KG_SSH_PORT` | `60005` |
| `KG_SSH_USER` | `dujx` |
| `KG_MACOS_KIT_SHA256` | YAML已固定当前运行包SHA-256；以后更新完整包时，从网站下载卡片或kit-reference.json核对后修改 |

工作台18765和模型18100继续只需在Linux本机可访问。SSH入口必须能从GitHub连接，并允许到以上端口的本地转发，以及监听Linux `127.0.0.1:32315` 的反向转发。

**本次已验证**：新CI密钥可以登录Linux本机SSH，并通过转发访问现有工作台。

**已实际验证的网络限制**：GitHub第一轮Mac直连 `tibaiot.7766.org:60005` 超时。该域名解析为校园网私网地址，当前先连接学校aTrust，再以实际SSH探测判断校园网资源是否可达。

## 第一次运行：只验证Linux与Mac双向SSH

1. 打开 https://github.com/duhhhh1/kg-macos-test/actions 。
2. 左侧点击 **macOS native commission tests**。
3. 点击 **Run workflow**。
4. 当前校园网方式将`phase`选择 **atrust-ssh-only**，再点击绿色 **Run workflow**。已经有可达SSH网络的环境可使用 **ssh-only**。
5. 等待本轮结束。它会完成：
   - Mac通过专用密钥登录Linux，转发工作台18765和模型18100；
   - Mac启动仅监听本机回环地址的临时sshd；
   - 同一个连接建立 `Linux 127.0.0.1:32315 → Mac临时SSH端口` 的反向隧道；
   - Linux使用留在服务器上的Mac控制密钥返回登录Mac；
   - 严格核对本轮Mac主机公钥、随机挑战、Darwin系统、实际macOS版本和架构；
   - 将连接报告与本轮日志保存到当前网站，然后关闭临时SSH服务和隧道。
6. 回到当前网站，点击 **平台实验与问答 → 日志与结果导入 → SSH执行与自动回收**，查看Mac→Linux和Linux→Mac结果。可直接展开日志、下载本轮Mac日志包。

Mac的临时sshd只接受专用公钥，强制执行固定的系统信息探测脚本，不提供交互式终端。此次检查不修改Mac全局“远程登录”设置。标准GitHub macOS runner具备无密码sudo，用于启动该临时服务。

`ssh-only`成功只表示双向连接完成。它不会生成2CA或3CA通过记录。

## 第二次运行：执行三领域项目测试

1. 确认上一次 `atrust-ssh-only`通过。
2. 再次 **Run workflow**，将`phase`改为 **atrust-full-tests**。已经有可达SSH网络的环境可使用 **full-tests**。
3. 工作流会再次验证双向SSH。只有本轮连接通过，才继续下载并校验完整运行包。
4. 在实际Mac上执行三领域环境、schema、Python API、CLI、retrieve、源行核验，以及每领域3条真实图文输入，共9条回答。
5. 核对原生完成摘要与平台证据SHA-256，再将平台JSON和完整原生结果ZIP回传当前工作台。
6. 打开当前网站 **平台实验与问答**，选择领域、点击 **macOS原生实验**，查看实际系统、检查结果、题干、原图、回答、知识依据和日志。
7. 打开Windows记录，展开“跨平台逐项核验依据”，下载完整对照报告。核心指纹复算、相同原图与三条完整回答全部一致时自动形成该组3CA通过；有回答文本差异时，再由实际复核人对照业务含义并记录结论。

`full-tests`成功以原生实际完成、回答完整、版本与输入绑定通过、结果导入成功为准。连接成功、下载成功或运行器显示macOS本身均不直接构成兼容性通过。

## 日志与公开仓库的展示范围

完整原图、问题、知识检索、模型回答和逐阶段日志保存到现有Linux工作台。网页支持按段查看及下载原始结果ZIP。连接成功后的失败轮次也会尝试回传日志，失败不会产生原生通过结论。

GitHub公开Artifact保存 `summary.json`，包括阶段、实际系统/架构、连接是否通过、原生是否完成、是否回传和退出码，保留7天。aTrust还保存不含账号的安装、签名与初始界面诊断；账号提交之后不保存界面截图或完整UI内容。未连上工作台的连接错误可在摘要查看；此时尚无项目题目或模型回答被执行。

Mac执行记录到达后自动出现在网页；讲解时无需登录GitHub查看答卷，也无需在Windows/Mac重新配置本地模型。

## 常见问题

| 现象 | 操作 |
| --- | --- |
| Actions列表没有工作流 | 检查YAML是否位于默认分支 `.github/workflows/commission-macos.yml`，并确认仓库Actions已启用 |
| Connection refused / timed out | 核对公网域名、端口映射和SSH服务；GitHub无法使用家庭192.168内网地址或Windows自己的127.0.0.1端口转发 |
| Permission denied (publickey) | 确认KG_CI_SSH_KEY是新CI密钥完整内容，公钥已授权到实际目标Linux用户，用户名正确 |
| Host key verification failed | 从可信连接重新核对实际入口主机公钥，更新KG_CI_SSH_KNOWN_HOSTS |
| remote port forwarding failed | 检查32315是否被占用、SSH是否允许远程转发，以及对应公钥permitlisten配置 |
| Mac临时SSH服务未启动 | 查看网页本轮mac-sshd.log；该入口依赖标准runner的无密码sudo和/usr/sbin/sshd |
| SSH通过但项目测试未通过 | 查看网页原生执行日志，按实际异常修复后重跑，保留失败轮次 |
| 原生完成但回传失败 | 该轮不宣称网站已导入；恢复工作台连接后重跑或补充导入本轮原始结果。公开Artifact不包含完整答卷 |

较早轮次的校园网入口超时记录仍保留。最新成功运行 **40184802632** 经Windows浏览器人工登录学校aTrust后，已完成双向SSH及三领域原生测试，实际 **macOS15.7.9 / ARM64 / Python3.11.17**。9条真实图文问答和完整日志已导入 **platform-c8407d5b0791**。三领域核心完整指纹复算及逐题回答/原图对照均通过；当前同版本累计42/42。
