# macOS通过哈工大aTrust直接连接服务器

本方式使用学校提供的aTrust客户端接入校园网，再通过原生SSH访问现有Linux服务器，调用现有模型并回传原生结果。无需经Windows中转，也无需让Mac加入Tailscale。

## 已确认的官方下载来源

- 哈工大入口：https://ivpn.hit.edu.cn
- 学校入口提供的Mac终端安装包：https://ivpn.hit.edu.cn/resource/client/mac/aTrustInstaller.pkg
- 深信服产品软件目录：https://support.sangfor.com.cn/productSoftware/list?product_id=19&category_id=160

产品软件目录中的“控制台灰度更新ZIP包”“服务端升级bin包”用于管理员升级部署。普通Mac终端应使用学校入口提供的PKG安装包，以匹配学校当前网关。

本次检查到的学校PKG为234726127字节，SHA-256为：

```text
d8f6866aac9407edf348fca1fd890d44fc6c63a1aea4bf92184f1d30a23b719d
```

静态安装包版本为2.5.16.31，主程序及隧道组件为Intel x86_64。Apple Silicon环境须以实际安装和Rosetta运行结果为依据。GitHub工作流会额外使用macOS的pkgutil检查SANGFOR安装签名；安装包内容变化时停止，重新核验后才能更新固定哈希。

## 实际Mac电脑的操作

1. 下载学校PKG，打开安装向导，按提示完成安装。
2. 启动aTrust，服务器地址填入 `https://ivpn.hit.edu.cn`。
3. 按学校统一身份认证页面登录你自己的账号。账号密码只填在官方登录界面。若出现验证码、扫码、二次认证或设备审批，按学校正常流程完成。
4. 在macOS系统设置中完成客户端实际提示的必要授权。不同Mac系统版本、CPU和学校策略可能有不同要求，以现场界面为准。
5. 看到客户端已连接后，在Mac本机终端测试已知SSH入口：

   ```bash
   ssh -o ConnectTimeout=10 -p 60005 dujx@tibaiot.7766.org
   ```

   使用你自己的、已授权的SSH认证方式。校园网账号认证与Linux SSH用户认证是两次独立认证。

6. 在Mac本机终端建立工作台与模型转发：

   ```bash
   ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=20 \
     -p 60005 \
     -L 28765:127.0.0.1:18765 \
     -L 28100:127.0.0.1:18100 \
     dujx@tibaiot.7766.org
   ```

7. 保留该终端，浏览器打开 `http://127.0.0.1:28765/#platform-experiments`。可以查看已有Windows结果并实时问答。
8. 在网页的“Windows/macOS测试运行包”下载Mac完整包，解压后在新的Mac本机终端进入解压目录，执行：

   ```bash
   bash ./start-macos-test.command \
     --dashboard-url http://127.0.0.1:28765 \
     --endpoint http://127.0.0.1:28100/v1/chat/completions
   ```

9. 等待三领域检查及实际图文回答完成。启动器保存每轮日志并尝试自动回传；回传成功后，在原网站选择“macOS原生实验”查看题干、原图、回答、检索和日志。

## GitHub标准macos-15的验证顺序

工作流增加 `atrust-preflight` 阶段，先在真实Mac检查学校客户端的下载、哈希、签名、安装与启动。该阶段不使用校园网账号，也不授予任何兼容性通过。

运行入口：https://github.com/duhhhh1/kg-macos-test/actions

选择 **macOS native commission tests → Run workflow → atrust-preflight**。首次实际运行号为 **40178251763**。原网站定期同步其真实状态、摘要与日志。

客户端可安装和启动，只是第一步。还必须验证：

1. 学校统一身份认证能在该临时Mac中按正常流程完成。
2. 客户端获得必要的系统权限、后台服务和校园网资源授权。
3. 接入后确实能够连接 `tibaiot.7766.org:60005`，并完成SSH身份验证。
4. Mac→Linux与Linux→Mac反向SSH挑战均通过。
5. 使用同版本交付包运行三领域原生项目，核对实际输入输出并导入原始证据。

如果实际登录要求验证码、扫码、人工审批或系统界面确认，需要在该步骤完成正常交互。安装成功、网页登录成功、VPN显示在线、SSH连接成功和原生项目测试通过，会分别记录，不能相互替代。

## 日志与凭据

客户端预检的公开Artifact只保存不含账号的系统、安装与启动结果，以及安装签名和组件信息。校园网密码、会话Cookie、客户端认证缓存不能放进公开Artifact或仓库。

现有网页 **平台实验与问答 → 日志与结果导入 → SSH执行与自动回收** 可查看本仓库实际运行记录。原生兼容性仅依据成功导入的实际Mac项目证据更新；跨平台一致性还需与Windows同版本记录逐项对照。
