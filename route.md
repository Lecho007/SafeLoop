# SafeLoop：基于判别反馈与协同进化的大语言模型闭环安全评估框架
# SafeLoop: A Judge-Guided Co-Evolutionary Red Teaming Framework for Large Language Model Safety Evaluation

# SafeLoop 路线文档

> 原项目（paper/，Legacy V0：DeepSeek-R1 红方 + MacBERT 15 类判别 + Flask/Vue 平台）不再修补。
> 按模型无关、闭环驱动、轨迹级、可逐步训练的架构重新组织，分 Stage 推进。
> 冻结原则（V0.3 起）：core/ 与 engine/episode_runner.py 不再改动，
> 变化限制在 adapter、benchmark、normalizer、config 层。

## 1. 研究问题

> 如何利用安全判别器反馈、历史攻击经验和风险边界信息，自适应地探索黑盒大语言模型的
> 安全漏洞，并利用新发现的困难样本反向提升安全判别器对未知风险的识别能力？

即 **Judge-Guided Adaptive Red Teaming + Bidirectional Co-evolution**。
Stage 1 只研究一个变量：**Feedback**（Memory/Scheduler/Training/DPO/RL 全 OFF）。

## 2. 设计原则（六条）

1. 模型无关：任务定义 → 机制 → 接口 → 模型选型（mechanism first, model second）。
2. 闭环端到端而非梯度贯通：Generate → Attack → Judge → Feedback → Adapt。
3. 研究对象是攻击轨迹 τ = {(s,a,p,y,o,r)}，不是单条 (text,label)。
4. Safety Judge 多维输出：Unsafe + Harm + Jailbreak + Refusal + Severity（+四级 outcome），
   字段级 provenance（native/derived_proxy/derived_rule/unavailable），缺数据为 None 不伪造。
5. 双闭环：内循环 Red→Target→Judge→Red；外循环 Red↔Judge 协同进化。
6. 渐进训练：Feedback → Memory → Scheduler → Hard Example → DPO → RL。

## 3. 阶段路线与当前状态

| Stage | 科学问题 | 状态 |
|-------|----------|------|
| 0 骨架 | 模型无关闭环跑通 | ✅ V0.1 |
| 1 Feedback Loop | 相同查询预算下判别反馈是否提升边界探索 | ✅ V0.2 协议层（demo 通过）→ ✅ V0.3 真实模型层代码就绪，**待下载权重后跑 1A** |
| 2 Memory | 历史攻击经验是否进一步提高效率 | 待启动 |
| 3 Risk Scheduler | 风险边界自适应调度 | 待启动 |
| 4 Judge Co-evolution | 难例回流提升 Judge | 待启动（disagreement 已落盘） |
| 5 Preference / 6 RL | DPO / PPO·GRPO | 待启动 |

## 4. V0.3 — Stage 1 轻量真实模型层（本期交付）

### 4.1 双硬件模型组合（V0.3.1，分时加载 + round-batched，Phase 间 empty_cache）

| 角色 | V100 32GB（服务器） | RTX 4060 Laptop 8GB（主开发机） | 量化策略 |
|------|--------------------|--------------------------------|----------|
| Red Agent G | Qwen3-4B | **Qwen3-1.7B** | FP16/BF16，不量化 |
| Target T | Mistral-7B-Instruct-v0.3 | **Phi-3.5-mini-instruct 3.8B** | **4-bit NF4**（compute bf16） |
| Feedback Judge J_f | Qwen3Guard-Gen-4B | **Qwen3Guard-Gen-0.6B** | FP16/BF16，不量化 |
| Independent Evaluator E | StrongREJECT-2B（离线） | StrongREJECT-2B（离线） | FP16（紧可 4-bit） |

原则：**只换模型实例化，不换科学问题**——数据集/条件/协议/指标完全相同；
量化只用于必要角色（Target），quantization/compute_dtype 记入 provenance，
所有条件使用同一量化实例。4060 档 BF16 优先，实测不兼容则统一降 FP16。
两档配置分离于 `configs/hardware/{v100_32g,rtx4060_8g}.yaml`，不混用。
J_f ≠ E 与 family(G) ≠ family(T) 两个实验原则在两档下均保持。

8GB 不再往下缩（0.6B Red + 2B Target）：那会改变研究问题本身。
1.7B Red + 3.8B Target 是轻量下限——Red 太小将无法区分「反馈没用」与「Agent 不理解反馈」。

Judge 校准数据已就位：`data/raw/jbb_judge_comparison.csv`（3677 条，
3 人工标注 + harmbench_cf/gpt4_cf/llamaguard2_cf/llama3_cf 对比标签）+
XSTest-Response（校准阶段再下）。Qwen3Guard-0.6B 先在标注子集校准，
明显不够再升 4B，而不是默认大模型。

Mistral 无 moderation 机制，只作 smoke target；1A 后执行 **Target Suitability Gate**：
ASR_C1@1 ≥ 0.80 或 ASR_C1@B ≥ 0.95 → ceiling；ASR_C1@B ≤ 0.05 → floor；
框架不改，只换更强对齐的 7B/8B Target。

### 4.2 Benchmark 层次（冻结，与硬件无关）
```
Track-EN: JBB-20(1A smoke) → JBB-100(1B 机制验证) → HarmBench-Val(1C-Dev 调参)
          → HarmBench-Test(1C-Test 冻结后正式) →（后期 SALAD-Bench taxonomy/scheduler）
Track-ZH: JailBench（主）→ CSEI-SafetyBench（显式→隐式泛化）   [英文机制跑通后开启]
Judge 校准: JBB judge-comparison（已下载）+ XSTest-Response
```
JBB 官方 CSV（harmful/benign/judge-comparison）已下载到 `data/raw/`，
manifest 已生成（jbb20/jbb100）。HarmBench 正式实验额外离线跑官方 classifier
（cais/HarmBench-Llama-2-13b-cls，benchmark-specific evaluator，非系统组件）。

### 4.3 实验条件
C0(B=1) / C1(B=5 无反馈，可见响应历史自我调整) / C2(分数) / C3(结构化，主方法) /
C_SR(红方自我反思 keep/refine/switch 基线，1C 用)。
硬约束：Judge 只指出策略维度（failure_type/adaptation_action），不生成攻击 prompt。
第 0 轮 prompt 跨条件完全一致（红方第 0 轮强制贪心 + 无 history/feedback）。
B = Target 查询数；Q_G/Q_T/Q_J/Q_E 分开统计。

### 4.4 本期新增代码
- **真实 Adapter**：`agents/hf_red_agent.py`（JSON 输出契约 + 解析重试 + 第 0 轮贪心不变量）、
  `targets/hf_target.py`（**支持 4-bit NF4 量化**，quantization/compute_dtype 入响应与
  provenance）、`agents/qwen_guard_judge.py`（XML 风险块解析 + 字段级 provenance
  normalizer）、`evaluation/strongreject_evaluator.py`（官方包优先，seq-cls fallback）。
- **V100/4060 分时加载**：`engine/hf_backend.py`（懒加载 + ModelManager 单驻留切换 +
  `quantization_spec` NF4 规范化，BitsAndBytes 懒导入）；
  **round-batched 执行器** `engine/batch_runner.py`（Red→Target→Judge→CPU 四相位）。
- **成本核算** `engine/cost.py`（Q_G/Q_T/Q_J/Q_E、token、重试、时延，写入 trajectory.cost）。
- **指标**：CTTS（截尾成功时间，失败=B+1）、FRR、ESSR + `evaluation/stats.py`
  （McNemar / Wilcoxon 符号秩，纯 stdlib）。
- **数据**：`data/adapters/jailbreakbench.py`（官方 CSV/JSON → SafetyTask 分层抽样）+
  jbb20/jbb100 manifest + judge-comparison 校准数据。
- **配置**：`configs/hardware/{v100_32g,rtx4060_8g}.yaml`（双档分离，protocol 完全一致）。
- **脚本**：run_stage1a（--dry-run，默认 4060 档）、build_jbb_tasks（--csv/--all/--demo）、
  check_weights（双档校验）、build_calibration_set（D_cal 分层抽样）。
- prompt 模板版本化：`prompts/red/real_v1.yaml`、`prompts/judge/qwenguard_v1.yaml`。

### 4.5 Dry-run 验证（无权重无 GPU，scripted 后端走同一 batch 管道）
20 tasks × C1/C3 × B=3：Q_T/Q_G/Q_J/Q_E 均恰 60；第 0 轮 prompt 一致；报告含
paired/McNemar/Wilcoxon/Gate/验收清单；轨迹带 cost 与 E 标签可恢复。
43 项单测全部通过（parser/stats/CTTS/FRR/ESSR/dry-run/双硬件配置等）。

### 4.6 Stage 1A 验收清单（不看论文结论，C3<C1 也 PASS）
模型加载/chat template/JSON 解析/查询记账正确；C1/C3 第 0 轮一致；E 不进 online loop；
replay 一致；provenance 完整；retry 不增加 Target query；无 OOM；trajectory 可恢复。
1A 后：Target ceiling/floor Gate + Judge 校准集 D_cal（100–200 条真实 response，
J_f vs E Agreement + 人工 audit + Type A/B 落盘）。

### 4.7 后续（权重就位后）
1A（真实 JBB-20，C1/C3，B=3）→ Gate/校准 → 1B（JBB-100，C1 vs C3，B=5，
seed 42→{42,123,2026}，Go/No-Go：ΔASR>0 且 ΔAUC-B>0 且机制指标支持）→
1C-Dev（HarmBench-Val 全条件含 C_SR）→ 冻结 → 1C-Test（HarmBench-Test）→
第二/三 Target 泛化 → Track-ZH。

## 5. 目录结构（模块直接位于 SafeLoop 主目录）

```
SafeLoop/
├── core/          schemas(V0.2+provenance/cost) / protocol / protocol_validator /
│                  coordinator(+impl) / reward          [冻结层]
├── engine/        episode_runner [冻结] / batch_runner / hf_backend / factory /
│                  provenance / replay / cost
├── agents/        base_red_agent / base_judge / red_agent(template) / hf_red_agent /
│                  safety_judge(rule) / qwen_guard_judge
├── targets/       base_target / scripted_target / hf_target
├── evaluation/    base_evaluator / demo_evaluator / strongreject_evaluator /
│                  offline_evaluator / metrics / stats
├── memory/  scheduler/  feedback/                      [V0.2 原样]
├── experiments/   conditions(C0–C3/C_SR/1A) / stage1 / stage1a
├── prompts/       red/{v1,real_v1}.yaml / judge/{v1,qwenguard_v1}.yaml /
│                  feedback/{score,outcome,structured}_v1.yaml
├── data/          tasks/{test,jbb20_demo}.jsonl / adapters/jailbreakbench.py /
│                  mappings/harm_taxonomy.yaml / calibration/
├── configs/       stage1.yaml(V0.2 demo) / hardware/{v100_32g,rtx4060_8g}.yaml
├── scripts/       run_experiment / run_episode / run_stage1a / build_jbb_tasks /
│                  check_weights / build_calibration_set / replay_trajectory
├── tests/         43 项（schemas/protocol/stage1/parsers/stats/metrics/dry-run/hardware）
├── weights/       red/ target/ judge/ evaluator/（见 setup_env.md 下载命令）
├── outputs/       trajectories / evaluations / disagreement / reports
├── paper/  route.md  setup_env.md  requirements.txt
```

## 6. 版本规划

```
V0.1 模型无关闭环骨架                              ✅
V0.2 Stage 1 实验协议（四条件/独立评估器/校验器/离线指标/Replay/Provenance）✅
V0.3 Stage 1 真实模型层（4 Adapter/分时加载/round-batched/成本/CTTS-FRR-ESSR/
     统计检验/JBB 适配/权重目录）                ✅
V0.3.1 双硬件档（RTX4060 8G：1.7B+Phi3.5-NF4+0.6B；量化入 provenance）✅（本期）
V0.4 Stage 1A/1B/1C 实验执行（权重就位后）
V0.5 多任务 Judge  |  V0.6 Attack Memory  |  V0.7 Risk Scheduler
V0.8 Independent Evaluator 完整版  |  V1.0 双向难例协同进化
V1.1 偏好学习（DPO）  |  V2.0 强化学习
```

## 7. 环境拆分（V100 服务器 / RTX4060 本地）

```text
safeLoop-core    # 当前：pyyaml 即可（框架/dry-run/分析）
safeLoop-train   # 1A 真实运行：torch 2.1 cu121 + transformers（Python 3.8 兼容版本）
safeLoop-eval    # 后期大规模评测
```
