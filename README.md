# kg-macos-test

番茄、生猪、鱼类知识图谱项目的 macOS 原生兼容性与真实图文功能测试。

工作流固定使用公开仓库的标准 `macos-15` runner。按GitHub官方当前说明，公开仓库标准runner运行时长免费；工作流手动触发、最长90分钟，状态摘要Artifact保留7天。

校园网环境支持Tailscale：设置 `KG_USE_TAILSCALE=true`，配置 `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET`，将SSH目标设为服务器Tailnet地址。步骤见 [Tailscale校园网接入指南](Tailscale_校园网与GitHub_Mac接入指南.md)。

## 配置和运行

1. 在 **Settings → Secrets and variables → Actions** 添加两个Repository Secrets：
   - `KG_CI_SSH_KEY`：新建的Mac→Linux专用登录私钥，来源见详细指南；不要提交到仓库。
   - `KG_CI_SSH_KNOWN_HOSTS`：已核验的Linux公网SSH入口主机公钥条目。
2. 默认服务器为 `dujx@tibaiot.7766.org:60005`。需要调整时配置 `KG_SSH_HOST`、`KG_SSH_PORT`、`KG_SSH_USER` Variables。当前完整测试包SHA-256已固定在YAML中。
3. 打开 **Actions → macOS native commission tests → Run workflow**，先选择 **ssh-only**。
4. 确认 **Mac→Linux** 与 **Linux→Mac反向SSH** 均通过，再运行 **full-tests**。
5. 项目测试通过后，平台证据与原始日志自动回传原有工作台，在 **平台实验与问答** 查看Mac和Windows结果，并完成跨平台业务复核。

原始交付包、图谱、图片、模型输入输出和完整日志通过SSH在runner与现有工作台之间传递。公开Artifact只保存小型状态摘要，不包含完整答卷或私钥。GitHub runner会在任务结束时回收，原有网站继续提供结果展示与实时问答。

详细步骤、Secrets来源、端口说明和故障排查见 [macOS GitHub Actions验证与接入指南](macOS_GitHub_Actions验证与接入指南.md)。

`ssh-only`验证连接，不生成macOS兼容性通过记录。`full-tests`在实际Mac运行三领域代码，通过原生结果与日志校验后才发布2CA；3CA还需与Windows同版本回答对照复核。

## 官方依据

- [标准GitHub-hosted runners与公开仓库免费说明](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [GitHub Actions计费说明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Runner环境与软件清单](https://github.com/actions/runner-images)
