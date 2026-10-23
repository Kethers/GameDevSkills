---
name: ue-commit-weekly-summary
description: "UE5/UE6 主分支每周提交总结工具。从工蜂内部镜像或 GitHub 获取 Unreal Engine ue5-main 和 ue6-main 分支的近7天提交记录，自动分析模块分布、作者统计、提交分类，生成三层结构的深度总结报告（宏观大盘、模块解读、趋势总结），通过分段 notify 推送并输出 Markdown/PDF 文件。触发场景：UE提交总结、UE周报、Unreal Engine 提交分析、ue5-main/ue6-main 提交拉取、引擎提交周度报告。适合配合定时任务每周一自动执行。"
---

# UE 主分支每周提交总结

从工蜂镜像仓库（或 GitHub 备选）拉取 UE5-Main / UE6-Main 分支近7天提交记录，分析后生成结构化周度总结报告。

## 依赖

- `mcporter-internal`（调用工蜂 API）— 内网安装：`npm install -g @tencent/mcporter-internal --registry=https://mirrors.tencent.com/npm`
- `md-to-pdf` skill（可选，生成 PDF）
- Python 3（运行分析脚本）
- `notify` 工具（推送报告）

## 执行流程

### 第一步：获取 ue5-main 提交（快速检查）

1. 计算时间范围：since = 7天前 00:00:00，until = 今天 23:59:59（北京时间 +0800）
2. 优先使用工蜂镜像获取：

```bash
bash scripts/fetch_gongfeng_commits.sh ue5-main 7 /tmp
```

3. **如果工蜂不可用**（mcporter-internal 服务异常或网络问题），提示用户切换到 GitHub：

```bash
# 需要用户提供 GitHub PAT（EpicGames/UnrealEngine 是私有仓库）
export GITHUB_TOKEN="ghp_xxx"
bash scripts/fetch_github_commits.sh ue5-main 7 /tmp
```

> GitHub 鉴权说明：EpicGames/UnrealEngine 是私有仓库，需要：
> 1. 在 https://www.unrealengine.com/ue-on-github 将 GitHub 账号绑定 Epic Games 账号
> 2. 在 https://github.com/settings/tokens 创建 PAT（Classic PAT 选 `repo` 权限，或 Fine-grained PAT 授予 EpicGames/UnrealEngine 只读权限）
> 3. 设置环境变量 `export GITHUB_TOKEN="ghp_your_token"`

4. 判断逻辑：
   - 无新提交 → 记录"ue5-main 本周无新提交"，跳过分析
   - 少量提交（< 30） → 简要列出主要改动方向
   - 大量提交（>= 30） → 按三层结构分析

### 第二步：获取 ue6-main 提交（主要分析对象）

```bash
# 工蜂
bash scripts/fetch_gongfeng_commits.sh ue6-main 7 /tmp

# 或 GitHub 备选
bash scripts/fetch_github_commits.sh ue6-main 7 /tmp
```

### 第三步：分析提交

运行分析脚本生成结构化 JSON：

```bash
python3 scripts/analyze_ue_commits.py --input-dir /tmp --output /tmp/ue_commits_analysis.json --branch ue6-main
```

读取输出的 JSON 文件，根据每个模块的 commit titles 撰写总结报告。

报告格式严格遵循三层结构，详见 [references/report-format.md](references/report-format.md)。

### 第四步：分段通知

拆分为多条 notify 推送，每条控制在 2000 字符以内。详见 [references/report-format.md](references/report-format.md) 的通知分段规则。

### 第五步：输出文件

1. 整合所有 notify 内容写入 Markdown 文件
2. 使用 `display_download_links` 提供下载
3. 尝试使用 `md-to-pdf` skill 转 PDF（失败不阻塞）

## 工蜂镜像参数

| 参数 | 值 |
|------|-----|
| project_id | `UnrealEngine/UnrealEngine-1` |
| 分支 | `ue5-main` / `ue6-main` |
| per_page | `100` |
| 时间格式 | `YYYY-MM-DDT00:00:00+08:00` |

## GitHub 备选参数

| 参数 | 值 |
|------|-----|
| 仓库 | `EpicGames/UnrealEngine`（私有） |
| 分支 | `ue5-main` / `ue6-main` |
| 鉴权 | `GITHUB_TOKEN` 环境变量（Bearer token） |
| API | `https://api.github.com/repos/EpicGames/UnrealEngine/commits` |

## 定时任务配置示例

每周一 09:30 自动执行：

```
cron: 30 9 * * 1
```

jobMessage 示例见完整的执行流程（第一步到第五步）。
