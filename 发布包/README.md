# CAET 发布包目录

正式可交付文件统一由 GitHub Actions 构建并保存到 GitHub Releases：

- `部署包/`：本地验包分类目录，正式 ZIP 在 GitHub Releases 下载。
- `修复包/`：本地修复包分类目录，代码改动通过 Pull Request 审核。

每次开发使用 `功能/名称`、`修复/名称` 或 `部署/版本` 中文分支。合并到 `main` 后推送 `v*` 标签，GitHub 会自动构建并创建 Release；ZIP 不提交到源码历史。

## 推荐正式发布流程

```powershell
git switch main
git pull --ff-only origin main
git tag -a v1.2.1 -m "正式发布 v1.2.1"
git push origin v1.2.1
```

随后前往 GitHub 仓库的 `Actions` 查看构建过程，到 `Releases` 下载 `CAET-v1.2.1.zip` 及 SHA256 校验文件。

## 示例

```powershell
# 生成并同步完整部署包
./scripts/生成发布包.ps1 -类型 部署包 -名称 正式环境 -版本 v1.2.1 -说明 '正式环境部署' -同步GitHub

# 生成功能修复包（相对 origin/main 收集改动）
./scripts/生成发布包.ps1 -类型 修复包 -名称 登录超时 -版本 v1.2.1-fix1 -说明 '修复登录状态提前失效' -同步GitHub
```

本地脚本仍可用于部署前验包或生成临时修复包；正式发布以 GitHub Releases 中的自动构建结果为准。
