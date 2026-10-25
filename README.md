# kg-macos-test

番茄、生猪、鱼类知识图谱项目的 macOS 原生兼容性与真实图文功能测试。

当前采用哈工大aTrust直接接入校园网，`KG_USE_TAILSCALE=false`。`atrust-preflight`检查客户端；`atrust-ssh-only`尝试一次正常账号登录并验证双向SSH；`atrust-full-tests`在连接通过后运行三领域原生测试。见 [aTrust校园网接入与验证指南](aTrust_macOS校园网接入与验证指南.md)。

人工登录选择 `atrust-manual`：准备限时、受本轮凭据保护的Mac画面，通过现有工作台 `/macos-manual` 在Windows浏览器操作。本人完成学校认证后点击“登录完成，继续测试”；校园网SSH和双向连接实际通过后才运行项目。该模式使用 `KG_MANUAL_ACCESS_TOKEN` Secret，不自动填写学校账号。登录等待30分钟，画面最长45分钟，临时HTTPS和私有截图缓存随任务关闭。

实际运行40184802632已完成上述流程：macOS15.7.9 / ARM64 / Python3.11.17，双向SSH通过，三领域9条实际图文回答及完整日志已回传。现有工作台原生记录为`platform-c8407d5b0791`，可以直接查看。该轮临时Mac已正常回收，网页问答继续使用现有服务器模型。

工作流固定使用公开仓库的标准 `macos-15` runner。按GitHub官方当前说明，公开仓库标准runner运行时长免费；工作流手动触发、最长90分钟，状态摘要Artifact保留7天。

Tailscale保留为可选接入方式；当前aTrust阶段跳过它，无需为本方式配置Tailscale账号或OAuth。可选方案见 [Tailscale校园网接入指南](Tailscale_校园网与GitHub_Mac接入指南.md)。

## 配置和运行

1. 在 **Settings → Secrets and variables → Actions** 添加两个Repository Secrets：
   - `KG_CI_SSH_KEY`：新建的Mac→Linux专用登录私钥，来源见详细指南；不要提交到仓库。
   - `KG_CI_SSH_KNOWN_HOSTS`：已核验的Linux公网SSH入口主机公钥条目。
   采用aTrust时另设 `HIT_VPN_USERNAME`、`HIT_VPN_PASSWORD`，来源是本人获授权的学校账号。仅存GitHub Secrets，不能写进源码、公开日志或Artifact。
2. 默认服务器为 `dujx@tibaiot.7766.org:60005`。需要调整时配置 `KG_SSH_HOST`、`KG_SSH_PORT`、`KG_SSH_USER` Variables。当前完整测试包SHA-256已固定在YAML中。
3. 打开 **Actions → macOS native commission tests → Run workflow**，校园网aTrust方式先选择 **atrust-ssh-only**。
4. 确认 **Mac→Linux** 与 **Linux→Mac反向SSH** 均通过，再运行 **atrust-full-tests**。已经有可达SSH网络的环境可分别使用 **ssh-only** 和 **full-tests**。
5. 项目测试通过后，平台证据与原始日志自动回传原有工作台，在 **平台实验与问答** 查看Mac和Windows结果，并完成跨平台业务复核。

原始交付包、图谱、图片、模型输入输出和完整日志通过SSH在runner与现有工作台之间传递。项目执行阶段的公开Artifact保存小型状态摘要；不登录账号的aTrust预检还保存安装、组件和初始界面诊断。不包含完整答卷、校园网凭据或私钥。GitHub runner会在任务结束时回收，原有网站继续提供结果展示与实时问答。

详细步骤、Secrets来源、端口说明和故障排查见 [macOS GitHub Actions验证与接入指南](macOS_GitHub_Actions验证与接入指南.md)。

`ssh-only`验证连接，不生成macOS兼容性通过记录。`full-tests`在实际Mac运行三领域代码，通过原生结果与日志校验后才发布2CA；3CA由现有工作台对照同版本核心、输入、原图和完整回答。原始核心指纹复算及全部回答逐项一致时自动记录该组一致性；回答文本有差异时需进一步业务复核。

## 官方依据

- [标准GitHub-hosted runners与公开仓库免费说明](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions计费说明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Runner环境与软件清单](https://github.com/actions/runner-images)
