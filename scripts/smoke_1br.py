# -*- coding: utf-8 -*-
"""前期验证：四分支各 2 tasks 真实 smoke（装配/初始 prompt/None 跳 judge/RNG）。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments import stage1br as S
from engine.factory import load_tasks
from memory.trajectory_store import TrajectoryStore
from utils.io import load_yaml
from utils.logging import setup_logging

setup_logging()
cfg = load_yaml("configs/hardware/rtx4060_8g_1br.yaml")
tasks = load_tasks(cfg)
content, goal = S._split_domains(tasks)
sub = {"A": content[:2], "B": content[:2], "C": goal[:2], "D": goal[:2]}
orig_split = S._split_domains

# smoke 检查点（不污染主实验检查点）
import engine.checkpoint as ckpt
orig_save = ckpt.save_checkpoint
def smoke_save(path, payloads):
    return orig_save(path.replace("stage1b_r_4060_", "smoke1br_"), payloads)
ckpt.save_checkpoint = smoke_save
S.save_checkpoint = smoke_save

results = {}
for br in ("A", "B", "C", "D"):
    branch_tasks = sub[br]
    ids = {t.task_id for t in branch_tasks}
    S._split_domains = (lambda t, _ids=ids: (
        [x for x in orig_split(t)[0] if x.task_id in _ids],
        [x for x in orig_split(t)[1] if x.task_id in _ids]))
    trajs = S.run_branch(cfg, tasks, br)
    results[br] = trajs

S._split_domains = orig_split

# ---- 协议验证 ----
print("\n==== smoke protocol checks ====")
# 1. 初始 prompt 跨模式一致（同域 A vs B、C vs D）
for none_br, act_br, dom in (("A", "B", "content"), ("C", "D", "goal")):
    p0 = {}
    for br in (none_br, act_br):
        for t in results[br]:
            p0[t.task.task_id] = t.steps[0].action.prompt
    ok = len(set(p0.values())) <= len(results[none_br])  # 同任务同 prompt
    pairs = [(t.task.task_id, t.steps[0].action.prompt == results[act_br][i].steps[0].action.prompt)
             for i, t in enumerate(results[none_br])]
    print("[{}] {} vs {} round-0 prompt identity: {}".format(
        "PASS" if all(x[1] for x in pairs) else "FAIL", none_br, act_br, pairs))

# 2. NONE 支 judge 零调用
for br in ("A", "C"):
    invoked = [s.judge_output.metadata.get("judge_invoked")
               for t in results[br] for s in t.steps]
    fb = [s.feedback is not None for t in results[br] for s in t.steps]
    print("[{}] branch {} judge_invoked all False: {} | feedback all None: {}".format(
        "PASS" if not any(invoked) and not any(fb) else "FAIL", br,
        not any(invoked), not any(fb)))

# 3. ACTIVE 支 judge 被调用且反馈非空
for br in ("B", "D"):
    fb_n = sum(1 for t in results[br] for s in t.steps if s.feedback is not None)
    total = sum(len(t.steps) for t in results[br])
    print("[{}] branch {} feedback present: {}/{}".format(
        "PASS" if fb_n == total else "FAIL", br, fb_n, total))

# 4. 路由日志字段
sample = results["B"][0].steps[0].action.metadata.get("routing", {})
need = {"observability_domain", "feedback_mode", "judge_invoked",
        "feedback_built", "feedback_exposed_to_red", "red_seed", "target_seed"}
print("[{}] routing log fields: {}".format(
    "PASS" if need <= set(sample.keys()) else "FAIL", sorted(sample.keys())))

# 5. RNG 种子跨分支同任务同轮一致（A vs B 同 task round0 red_seed）
sa = {t.task.task_id: t.steps[0].action.metadata["routing"]["red_seed"]
      for t in results["A"]}
sb = {t.task.task_id: t.steps[0].action.metadata["routing"]["red_seed"]
      for t in results["B"]}
same = all(sa[k] == sb[k] for k in sa)
print("[{}] red_seed cross-branch identity (A vs B): {}".format(
    "PASS" if same else "FAIL", same))
print("\nsmoke done: " + json.dumps(
    {br: len(results[br]) for br in results}))
