# 贡献约定 · Git Flow

本仓是公开学习仓库。所有改动走 **Git Flow**，禁止在 `main` / `develop` 上直接堆提交。

## 分支模型

| 分支 | 角色 | 谁能动 |
|---|---|---|
| `main` | 稳定可对照的发布线；只接受 release / hotfix 合入 | 合入后打 `v*` tag |
| `develop` | 日常集成线；功能合入的默认目标 | 只接受已完成的 feature / bugfix |
| `feature/<name>` | 新知识点、文档、小改进 | 从 `develop` 拉出，合回 `develop` |
| `bugfix/<name>` | 非紧急缺陷 | 从 `develop` 拉出，合回 `develop` |
| `release/<version>` | 发布前整理（版本号、README、changelog） | 从 `develop` 拉出；合入 `main` **和** `develop` |
| `hotfix/<name>` | 已发布线上的紧急修复 | 从 `main` 拉出；合入 `main` **和** `develop` |

## 日常流程（必做）

```bash
# 1. 同步 develop
git checkout develop
git pull origin develop

# 2. 开功能分支（名字用短横线，说明意图）
git checkout -b feature/fix-readme-paths

# 3. 小步提交（一条提交只做一件事）
git add -p
git commit -m "docs: fix quick-start path in README"

# 4. 推远程并开 PR → base = develop
git push -u origin HEAD
gh pr create --base develop --title "docs: fix README paths" --body "..."

# 5. PR 合入后删本地/远程 feature 分支
git checkout develop
git pull origin develop
git branch -d feature/fix-readme-paths
git push origin --delete feature/fix-readme-paths
```

## 发布流程

```bash
git checkout develop && git pull
git checkout -b release/0.2.0
# 只做版本号 / 文档整理 / 冒烟，不塞新功能
git checkout main && git merge --no-ff release/0.2.0
git tag -a v0.2.0 -m "v0.2.0"
git checkout develop && git merge --no-ff release/0.2.0
git push origin main develop --tags
git branch -d release/0.2.0
```

## 硬规则

1. **不要**直接 `commit` 到 `main` 或 `develop`。
2. **不要** force-push `main` / `develop`。
3. 合入优先 **PR（`--no-ff` 或 GitHub merge commit）**，保留分支历史可读。
4. 提交信息用约定式前缀：`feat:` / `fix:` / `docs:` / `test:` / `chore:` / `refactor:`。
5. Agent / 自动化同样遵守：先开 `feature/*`，再合 `develop`；需要上 `main` 时走 `release/*` 或 `hotfix/*`。

## 本机 git-flow 前缀（可选）

若安装了 [git-flow AVH](https://github.com/petervanderdoes/gitflow-avh)：

```bash
git flow init -d   # master→main 时按提示改成 main
# 或与本仓一致的前缀：feature/ bugfix/ release/ hotfix/  versiontag=v
```

未装 CLI 时，用上面的手写命令即可，语义相同。
