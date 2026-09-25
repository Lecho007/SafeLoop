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
python -m unittest discover -s tests    # 145 项全过
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
pip install -r requirements.txt        # pyyaml + rich（框架/dry-run/分析/终端 CLI）
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

# 单元测试（145 项；框架层需 pyyaml + rich，见 requirements.txt）
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

# Stage 1B-A（判别器可观测子集 70 tasks × C1/C3 × B=5，10–12h，过夜跑）
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True nohup $PY scripts/run_stage1a.py \
    --config configs/hardware/rtx4060_8g_1ba.yaml > outputs/logs/stage1b_a.log 2>&1 &
# 断点续跑：每个 round 完成后自动原子落盘 outputs/checkpoints/<exp>.json；
# 中断后（断电/崩溃/手动停止）加 --resume 从最近完成轮次继续：
#   $PY scripts/run_stage1a.py --config configs/hardware/rtx4060_8g_1ba.yaml --resume

# ===== 黑盒 API Target（v1.0：接入任意远端模型）=====
# 三种协议：openai_chat（/chat/completions，兼容 vLLM/LiteLLM/网关，最广）/
#          anthropic（/messages，Claude 原生）/ openai_responses（/responses，OpenAI 新）
# Key 只经环境变量（永不写入任何落盘文件）：
export TARGET_API_KEY="sk-..."
# 连通测试（无害 ping）：
PYTHONPATH=. python3 apps/cli/safeloop_cli.py test-connection \
    --base-url https://api.example.com/v1 --model my-model --provider openai_chat
# 黑盒评估（小子集演示）：
PYTHONPATH=. $PY apps/cli/safeloop_cli.py api-eval \
    --base-url https://api.example.com/v1 --model my-model \
    --provider openai_chat --mode standard --max-tasks 3 --test-connection
# API 侧：POST /targets/test-connection（body: provider/base_url/model/api_key_env）
#         POST /evaluations 增加可选 api_target 字段
# 配置式（configs）：
#   target: {backend: api, provider: openai_chat,
#            base_url: https://…/v1, model: my-model,
#            api_key_env: TARGET_API_KEY,
#            generation: {temperature: 0.7, max_tokens: 4096, timeout: 60, retries: 3}}
#            ↑ max_tokens 默认已 4096（82c027d）：推理型模型（deepseek-flash/reasoner）
#              的思考链消耗同一 completion 预算，旧默认 512 会把最终回答截成空

# ================= SafeLoop v1.0 作品层（2026-09-25，d72323c）=================
# Workbench GUI（浏览器四页工作台：输入→多智能体运行视图→轨迹证据链→报告）
PYTHONPATH=. $PY -m streamlit run apps/workbench/app.py --server.port 8510
# 浏览器打开 http://localhost:8510 —— 默认回放 1B-R 预跑数据（秒级）；
# 也可选"现场真跑（小子集）"。

# API（FastAPI + SSE）
PYTHONPATH=. $PY -m uvicorn apps.api.server:app --port 8712
#   POST /replay                    —— 预跑数据装载为 run
#   POST /evaluations               —— 新建评估（standard/guided/compare）
#   GET  /evaluations/{id}/events   —— SSE 实时事件流
#   GET  /evaluations/{id}/{report|trajectories|tasks}
# 注：本机 curl 需 --noproxy '*'（系统代理会拦 127.0.0.1）

# CLI
PYTHONPATH=. python3 apps/cli/safeloop_cli.py report stage1b_r_4060   # 预跑报告
PYTHONPATH=. $PY apps/cli/safeloop_cli.py evaluate --mode compare --max-tasks 4  # 现场小子集

# 终端工作台（2026-09-25，af8f42f：向导式 CLI GUI + rich 实时对话流 + 彩色结果报告）
# 必须在 safeLoop 环境跑（引擎要 transformers——base 环境只装了 rich，跑到引擎才报错）
PYTHONPATH=. $PY apps/cli/workbench_cli.py                       # 交互向导：目标→模式→场景数
PYTHONPATH=. $PY apps/cli/workbench_cli.py --mode standard -n 3   # 带参数直接跑（可加 --suite/--config/--budget）
# DeepSeek 等推理型黑盒（key 只经环境变量；回答预算默认 4096，思考链不会截空回答）：
export TARGET_API_KEY="sk-..."
PYTHONPATH=. $PY apps/cli/workbench_cli.py \
    --base-url https://api.deepseek.com/v1 --model deepseek-flash --mode standard -n 3
# 重渲染已保存的报告 JSON：
PYTHONPATH=. $PY apps/cli/workbench_cli.py report outputs/reports/run-x_report.json
# 结果解读：判别列=Qwen3Guard 过程观察（Unsafe≠风险）；E 列=StrongREJECT 最终裁决
# （风险只数 E:风险确认）；出现"（空回答）"轮次时结论偏乐观，需调大回答预算重跑

# Stage 1B-R 主实验（任务感知反馈路由：4 causal branches × 1000 queries，单夜跑）
setsid nohup bash scripts/run_1br.sh > outputs/logs/stage1b_r.log 2>&1 < /dev/null &
# 顺序：A(content·NONE)→B(content·ACTIVE)→C(goal·NONE)→D(goal·ACTIVE·CF-10)
#       →EVAL(StrongREJECT)→SHADOW(goal 离线影子重判)→REPORT(三条件组装+R-H1~H5)
# 崩溃自动重启（始终 resume）；中断后重跑同命令即续。
# 进度条（另开终端）：bash scripts/watch_1br_progress.sh

# Stage 1B-CP（控制策略验证：refine-first + delayed switch，150 queries）
setsid nohup bash scripts/run_cp.sh > outputs/logs/stage1b_cp.log 2>&1 < /dev/null &
# 断点续跑 + 崩溃自动重启（5 次）；报告 outputs/reports/stage1b_cp_4060.json

# Stage 1B-B（任务感知多信号判别器：30 goal-compliance × B0/B-C/B-G/B-M × B=5）
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True PYTHONPATH=. nohup $PY -c \
    "from experiments.stage1bb import main; main()" > outputs/logs/stage1b_b.log 2>&1 &

# 1B-A 归档统计（Wilson CI/bootstrap/EAR/风险率/FRR 分解）
PYTHONPATH=. python3 scripts/archive_1ba_stats.py

# Gate J2 refusal 校准（xstest-response 449 条真标注）
PYTHONPATH=. $PY scripts/calibrate_refusal.py            # GPU；主实验运行中用 --device cpu --dtype float32

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
