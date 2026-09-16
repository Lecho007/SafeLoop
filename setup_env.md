# SafeLoop 命令文档 环境配置指南

## 环境配置指南
```bash
# 创建虚拟环境
mamba create -n safeLoop python=3.8 -y

# 激活环境
mamba activate safeLoop

# 安装基础依赖
pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 -i https://download.pytorch.org/whl/cu121 -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

mamba install pip numpy pandas opencv -c conda-forge -y
```

## 模型权重下载（V100 32GB，FP16 分时加载）

四个模型权重分别放入以下目录（目录已建好，直接下载到对应位置）：

| 角色 | 模型 | 存放目录 |
|------|------|----------|
| Red Agent | `Qwen/Qwen3-4B` | `weights/red/Qwen3-4B/` |
| Target | `mistralai/Mistral-7B-Instruct-v0.3` | `weights/target/Mistral-7B-Instruct-v0.3/` |
| Judge | `Qwen/Qwen3Guard-Gen-4B` | `weights/judge/Qwen3Guard-Gen-4B/` |
| Evaluator | StrongREJECT 微调 Gemma-2B | `weights/evaluator/strongreject-gemma-2b/` |

下载命令（在 SafeLoop 主目录下执行；服务器能连 HF 就用方案 A，否则方案 B）：

```bash
# 方案 A：huggingface-cli（pip install -U "huggingface_hub[cli]"）
huggingface-cli download Qwen/Qwen3-4B --local-dir weights/red/Qwen3-4B
huggingface-cli download mistralai/Mistral-7B-Instruct-v0.3 --local-dir weights/target/Mistral-7B-Instruct-v0.3
huggingface-cli download Qwen/Qwen3Guard-Gen-4B --local-dir weights/judge/Qwen3Guard-Gen-4B

# StrongREJECT：官方 pip 包 strong-reject 的权重（gemma-2b 微调），
# 按官方仓库说明导出到本地：
pip install strong-reject
# 若官方包只提供在线加载，则把其权重缓存目录内容复制到：
#   weights/evaluator/strongreject-gemma-2b/
# （代码优先用官方包；无包时回退 AutoModelForSequenceClassification 读该目录）

# 方案 B：镜像（HF-Mirror）
HF_ENDPOINT=https://hf-mirror.com huggingface-cli download Qwen/Qwen3-4B --local-dir weights/red/Qwen3-4B
# 其余三个同理

# 下载完成后校验（应输出 weight check: PASS）
python scripts/check_weights.py
```

## SafeLoop-core 框架层依赖

```bash
pip install -r requirements.txt        # 目前仅 pyyaml（框架/dry-run/分析）
```

真实运行（Stage 1A）额外需要（Python 3.8 兼容版本，逐项确认后再装）：
```bash
pip install "transformers>=4.45,<4.57" accelerate    # Qwen3 支持需较新版本
pip install strong-reject                            # StrongREJECT 官方包（可选）
```

环境拆分建议：`safeLoop-core`（框架/分析）/ `safeLoop-train`（真实运行+训练）/ `safeLoop-eval`。

## 常用命令（均在 SafeLoop 主目录下执行）

```bash
# 单元测试（35 项：schemas/protocol/stage1/parsers/stats/CTTS-FRR-ESSR/dry-run）
python -m unittest discover -s tests -v

# Stage 1A dry-run（无权重无 GPU，scripted 后端走同一 round-batched 管道）
python scripts/run_stage1a.py --dry-run

# Stage 1A 真实运行（需权重 + GPU；20 tasks × C1/C3 × B=3 = 120 Target queries）
python scripts/run_stage1a.py --config configs/stage1a.yaml

# 生成 JBB 任务 manifest
python scripts/build_jbb_tasks.py --demo --out data/tasks/jbb20_demo.jsonl   # 占位
python scripts/build_jbb_tasks.py --source /path/to/jailbreakbench.json \
    --per-category 2 --out data/tasks/jbb20.jsonl                            # 真实 JBB

# 权重完整性校验
python scripts/check_weights.py

# V0.2 四条件 demo 实验 / 单 episode / replay（保持可用）
python scripts/run_experiment.py [configs/stage1.yaml]
python scripts/run_episode.py [configs/stage1.yaml] [C0|C1|C2|C3] [task_index]
python scripts/replay_trajectory.py outputs/trajectories/<file>.jsonl --level structured

# Judge 校准集（1A 完成后）
python scripts/build_calibration_set.py outputs/evaluations/stage1a_smoke_C3.jsonl \
    --size 100 --out data/calibration/d_cal.jsonl
```

## 产物位置

```text
outputs/trajectories/*.jsonl   # 完整轨迹（judge/E 标签/provenance/cost）
outputs/evaluations/*.jsonl    # 离线评估后的轨迹副本（按条件）
outputs/disagreement/*.jsonl   # Judge vs E 不一致（Type A/B → Stage 4 难例）
outputs/reports/*.json         # 实验报告（协议校验/指标/配对检验/Gate/成本）
data/tasks/jbb20*.jsonl        # JBB 任务 manifest
```

## 真实后端切换（configs/stage1a.yaml，只改配置不改源码）

```yaml
red_agent:
  backend: hf            # weights/red/Qwen3-4B
target:
  backend: hf            # weights/target/Mistral-7B-Instruct-v0.3
judge:
  backend: qwen3guard    # weights/judge/Qwen3Guard-Gen-4B
evaluator:
  backend: strongreject_ft  # weights/evaluator/strongreject-gemma-2b
# 统一 dtype: float16（V100 不用 BF16）；Target 贪心 do_sample=false
```
