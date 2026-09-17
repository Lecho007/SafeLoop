# SafeLoop 命令文档 环境配置指南

## 环境配置（2026-09-17 最终锁定，Python 3.10，全部实测可用）

> ⚠️ 版本变更履历（为什么不是最初计划的 py3.8 + torch 2.1.0）：
> 1. Python 3.8 → 3.10：Qwen3 架构需要 transformers ≥ 4.51，而 transformers 4.49 起
>    放弃 py3.8（实测 4.46.3 报 "model type qwen3 not recognized"）；
> 2. torch 2.1.0 → **2.1.2**：transformers 的 SDPA attention 要求 torch ≥ 2.1.1，
>    而 4-bit Target 必须走 SDPA（eager attention 的 fp16 大矩阵 matmul 在 4060 上
>    触发 CUBLAS_STATUS_EXECUTION_FAILED，Stage 1A 首跑实锤）；
> 3. numpy 锁 1.26.x：torch 2.1.x 按 numpy 1.x 编译，numpy 2.x 报 _ARRAY_API 错。

```bash
mamba create -n safeLoop python=3.10 -y
mamba activate safeLoop

# 实测锁定版本（RTX 4060 Laptop / WSL2 / CUDA 可用）
pip install torch==2.1.2 transformers==4.53.2 peft==0.15.2 accelerate==1.7.0 bitsandbytes==0.45.5 pyyaml -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install "numpy<2"     # 装成 numpy 1.26.4

# 版本冻结清单（升级任何一个前先看理由）：
#   transformers==4.53.2  Qwen3/Qwen3Guard/Phi-3.5/gemma 支持 + py3.10 可用
#   torch==2.1.2+cu121    SDPA 需 >=2.1.1；cu121 runtime 与新驱动向后兼容
#   peft==0.15.2          StrongREJECT LoRA 本地加载/合并
#   bitsandbytes==0.45.5  Target 4-bit NF4
#   accelerate==1.7.0     device_map 加载路径
#   numpy<2               torch 2.1.x 编译兼容

# 环境自检（应全部输出正常）
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
python -c "import torch; x=torch.randn(4,4,dtype=torch.bfloat16).cuda(); print(torch.nn.functional.scaled_dot_product_attention(x,x,x).shape)"
python -m unittest discover -s tests    # 52 项全过
```

环境路径：`/home/MMCP/miniforge3/envs/safeLoop`（下文以 `$PY` 代指
`/home/MMCP/miniforge3/envs/safeLoop/bin/python`，或先 `mamba activate safeLoop`）。

长跑（Stage 1A/R2 级别）建议带防碎片分配器：
```bash
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY scripts/run_stage1a.py ...
```

> CUDA 兼容提示：驱动显示的 CUDA 版本（如 13.x）高于 PyTorch 自带 runtime（cu121）无需处理，
> 只要 `torch.cuda.is_available() == True` 且基础 tensor 测试正常就继续用。

## 双硬件配置档（configs/hardware/，不混用）

| 档位 | 配置文件 | 组合 |
|------|----------|------|
| **RTX 4060 Laptop 8GB（主开发）** | `configs/hardware/rtx4060_8g.yaml` | Qwen3-1.7B(bf16) → Phi-3.5-mini(**NF4**) → Qwen3Guard-0.6B(bf16) + StrongREJECT-2B(bf16 离线) |
| V100 32GB（服务器） | `configs/hardware/v100_32g.yaml` | Qwen3-4B → Mistral-7B → Qwen3Guard-4B + StrongREJECT-2B（全 FP16） |

量化策略：只量化 Target（NF4，compute bf16）；Red/Judge 不量化；E 离线 bf16。
4060 档 BF16 实测不兼容时，把 red/judge 的 dtype 统一降 float16。

## 模型权重（RTX 4060 档已全部下载就位，共约 17.6G，check_weights PASS）

| 角色 | 模型 | 目录 | 大小 |
|------|------|------|------|
| Red Agent | `Qwen/Qwen3-1.7B` | `weights/red/Qwen3-1.7B/` | 3.8G |
| Target | `microsoft/Phi-3.5-mini-instruct` | `weights/target/Phi-3.5-mini-instruct/` | 7.2G |
| Judge | `Qwen/Qwen3Guard-Gen-0.6B` | `weights/judge/Qwen3Guard-Gen-0.6B/` | 1.5G |
| Evaluator(LoRA) | `qylu4156/strongreject-15k-v1` | `weights/evaluator/strongreject-gemma-2b/` | 59M |
| Evaluator 底座 | `google/gemma-2b`（gated，已下载） | `weights/evaluator/gemma-2b-base/` | 5G |

StrongREJECT 官方实现 = gemma-2b 底座 + PEFT LoRA；打分逻辑已按官方源码移植到
`evaluation/strongreject_evaluator.py`，模板版本化于 `prompts/evaluator/strongreject_v1.yaml`。
如需在其他机器重下 gated 底座：
```bash
# 先在 HF 接受 google/gemma-2b 协议，然后：
HF_TOKEN=hf_xxx hf download google/gemma-2b --local-dir weights/evaluator/gemma-2b-base
```

**V100 档（服务器，按需再下）**：
`weights/red/Qwen3-4B/`、`weights/target/Mistral-7B-Instruct-v0.3/`、`weights/judge/Qwen3Guard-Gen-4B/`
（Evaluator 的 LoRA 与 gemma-2b 底座两档共用）。命令同下。

**通用下载命令**（注意：新版 huggingface_hub 的 CLI 是 `hf`，`huggingface-cli` 已弃用）：

```bash
hf download Qwen/Qwen3-1.7B --local-dir weights/red/Qwen3-1.7B
hf download microsoft/Phi-3.5-mini-instruct --local-dir weights/target/Phi-3.5-mini-instruct
hf download Qwen/Qwen3Guard-Gen-0.6B --local-dir weights/judge/Qwen3Guard-Gen-0.6B
hf download qylu4156/strongreject-15k-v1 --local-dir weights/evaluator/strongreject-gemma-2b
# 镜像：HF_ENDPOINT=https://hf-mirror.com hf download ...
python scripts/check_weights.py    # 完成后校验
```

## SafeLoop-core 框架层依赖

```bash
pip install -r requirements.txt        # 仅 pyyaml（框架/dry-run/分析，系统 python 即可）
```

GPU 真实运行的全部依赖已包含在上面的锁定版本里（transformers/peft/bitsandbytes/accelerate）。
环境拆分建议：`safeLoop-core`（框架/分析）/ `safeLoop`（真实运行，py3.10）/ `safeLoop-train`（后期训练）。

## 数据集（已下载并生成 manifest）

```text
data/raw/jbb_harmful_behaviors.csv    # JBB 官方 100 条 misuse behaviors（HF JBB-Behaviors）
data/raw/jbb_benign_behaviors.csv     # 100 条 benign（留作 OverRefusal/Judge sanity，不进主实验）
data/raw/jbb_judge_comparison.csv     # 3677 条 judge 对比数据（3 人工 + 4 自动 judge，用于 J 校准）
data/tasks/jbb20.jsonl                # Stage 1A：10 类 × 2 分层抽样（已生成）
data/tasks/jbb100.jsonl               # Stage 1B：全量 100 条（已生成）
data/tasks/jbb20_demo.jsonl           # 占位任务（无数据集时的管道 smoke）
```

重新生成命令：
```bash
python scripts/build_jbb_tasks.py --per-category 2 --out data/tasks/jbb20.jsonl
python scripts/build_jbb_tasks.py --all --out data/tasks/jbb100.jsonl
```
HarmBench-Val/Test、XSTest-Response 与中文（JailBench/CSEI-SafetyBench）按路线在
Stage 1C / Judge 校准 / Track-ZH 阶段再下载。

## 常用命令（均在 SafeLoop 主目录下执行）

```bash
# 环境变量（二选一）：
export PY=/home/MMCP/miniforge3/envs/safeLoop/bin/python   # 或 mamba activate safeLoop

# 单元测试（43 项；框架层用系统 python 即可）
python -m unittest discover -s tests -v

# Stage 1A dry-run（无权重无 GPU，scripted 后端走同一 round-batched 管道）
$PY scripts/run_stage1a.py --dry-run   # 默认 configs/hardware/rtx4060_8g.yaml

# 小规模真实 smoke（2 tasks × C1/C3 × B=3，约 12 分钟，用于运行前自检）
$PY scripts/run_stage1a.py --config configs/hardware/rtx4060_smoke2.yaml

# Stage 1A 完整真实运行（JBB-20 × C1/C3 × B=3 = 120 Target queries，约 2 小时）
nohup $PY scripts/run_stage1a.py --config configs/hardware/rtx4060_8g.yaml \
    > outputs/logs/stage1a_4060.log 2>&1 &
tail -f outputs/logs/stage1a_4060.log            # 监控进度（round= 行）
grep -c "round=" outputs/logs/stage1a_4060.log   # 已完成轮数（满 120 结束）
pkill -f run_stage1a.py                          # 需要中断时

# 权重完整性校验（含 gemma-2b gated 底座检查）
python scripts/check_weights.py configs/hardware/rtx4060_8g.yaml

# V0.2 四条件 demo 实验 / 单 episode / replay（保持可用）
python scripts/run_experiment.py [configs/stage1.yaml]
python scripts/run_episode.py [configs/stage1.yaml] [C0|C1|C2|C3] [task_index]
python scripts/replay_trajectory.py outputs/trajectories/<file>.jsonl --level structured

# ---- V0.3-J Judge Recovery（修复后 Judge，均离线，不调 Target）----
export PYTHONPATH=.
$PY scripts/calibrate_judge.py                    # Calibration-A：官方 300 条 vs 人类
$PY experiments/stage1aj.py                       # J0/J1/J2 对照（冻结 120 条响应）+ Gate
$PY scripts/reevaluate.py outputs/trajectories/<exp>_C1.jsonl outputs/trajectories/<exp>_C3.jsonl
                                                  # goal 基准重评（原文件备份 .bak）

# Stage 1A-R2（judge v2 + feedback v2，其余与 1A 完全一致）
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY scripts/run_stage1a.py \
    --config configs/hardware/rtx4060_8g_r2.yaml

# Judge 校准集（1A 完成后）
python scripts/build_calibration_set.py outputs/evaluations/stage1a_smoke_4060_C3.jsonl \
    --size 100 --out data/calibration/d_cal.jsonl
```

## 真实运行调通记录（2026-09-16，2-task smoke 已全链路验收）

smoke 结果：协议校验 PASS、第 0 轮 prompt 跨条件一致、四模型分时加载正常、
token/查询记账完整、StrongREJECT 离线评估正常、Target Gate=**SUITABLE**
（Phi-3.5 有部分抵抗力，无 ceiling/floor）；机制信号正确（C1 SSR=0，C3 SSR=1.0）。
调通过程中修复的问题（代码已固化，重跑无需处理）：

```text
1. Qwen3/Qwen3Guard chat template 默认开 thinking → chat_generate 传 enable_thinking=False
   （模板不支持该参数的模型自动回退）；
2. Qwen3-1.7B 偶发输出畸形 JSON（如 "prompt"> …，冒号误写、未闭合）→
   parse_red_json 三级解析：扁平对象扫描 → 字段正则 → 宽容提取，失败记 WARNING 并重试；
3. StrongREJECT LoRA 加载改为本地 PeftModel.from_pretrained + merge_and_unload
   （原 AutoPeftModel 会试图从 Hub 拉 gemma 底座）；
4. 期望分权重的 tensor device 与 logits 对齐；
5. red 模板中字面 JSON 花括号转义（{{ }}），避免被 .format() 当占位符。
```

## 产物位置

```text
outputs/trajectories/*.jsonl   # 完整轨迹（judge/E 标签/provenance/cost）
outputs/evaluations/*.jsonl    # 离线评估后的轨迹副本（按条件）
outputs/disagreement/*.jsonl   # Judge vs E 不一致（Type A/B → Stage 4 难例）
outputs/reports/*.json         # 实验报告（协议校验/指标/配对检验/Gate/成本）
data/tasks/jbb20*.jsonl        # JBB 任务 manifest
```

## 真实后端（configs/hardware/*.yaml，只改配置不改源码）

```yaml
red_agent:
  backend: hf            # 4060: weights/red/Qwen3-1.7B | v100: weights/red/Qwen3-4B
target:
  backend: hf            # 4060: Phi-3.5-mini（quantization: nf4）| v100: Mistral-7B
judge:
  backend: qwen3guard    # 4060: Qwen3Guard-Gen-0.6B | v100: Qwen3Guard-Gen-4B
evaluator:
  backend: strongreject_ft  # LoRA + base_model_path（gemma-2b 底座）
```
