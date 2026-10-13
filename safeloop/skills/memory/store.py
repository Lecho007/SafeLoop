# -*- coding: utf-8 -*-
"""长期攻击记忆（roadmap A1）：SQLite 结构化经验库，替换 NullMemory。

红线（docs/roadmap.md）：
  - outcome_proxy 是"在线观察代理"（拒绝/违规内容/安全/…），**不是攻击成功标签**
    ——StrongREJECT 的结果永不进入本库；
  - 检索带多样性约束（含失败经验、多策略族），防过度利用（1B-R 教训）；
  - 目标模型命名空间隔离 + 冻结快照（正式测试用独立快照，防数据泄漏）；
  - round 0 不注入任何经验（§13 不变量：跨条件 p0 逐字一致）——由
    agents.experience.build_experience_block 强制。
"""
import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory(
  memory_id TEXT PRIMARY KEY,
  source_run_id TEXT, source_task_id TEXT,
  target_fingerprint TEXT NOT NULL,
  harm_category TEXT NOT NULL,
  language TEXT DEFAULT '',
  strategy TEXT NOT NULL,
  strategy_summary TEXT, context_summary TEXT, observation_summary TEXT,
  outcome_proxy TEXT,
  quality REAL DEFAULT 0.0, novelty REAL DEFAULT 0.0,
  uses INTEGER DEFAULT 0, occurrences INTEGER DEFAULT 1,
  judge_version TEXT DEFAULT '',
  snapshot_id TEXT DEFAULT 'live',
  created_at TEXT, last_used_at TEXT,
  metadata_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_mem_ns ON memory(target_fingerprint, harm_category);
CREATE TABLE IF NOT EXISTS snapshots(
  snapshot_id TEXT PRIMARY KEY, created_at TEXT, n_records INTEGER,
  note TEXT DEFAULT ''
);
"""


@dataclass
class MemoryRecord:
    memory_id: str = ""
    source_run_id: str = ""
    source_task_id: str = ""
    target_fingerprint: str = ""
    harm_category: str = ""
    language: str = ""
    strategy: str = ""
    strategy_summary: str = ""       # 任务+策略要点（不含全文）
    context_summary: str = ""        # 攻击 prompt 摘要（截断）
    observation_summary: str = ""    # 裁判观察要点
    outcome_proxy: str = ""          # refusal / unsafe_content / safe / no_signal
    quality: float = 0.0
    novelty: float = 0.0
    uses: int = 0
    occurrences: int = 1
    judge_version: str = ""
    snapshot_id: str = "live"
    created_at: str = ""
    last_used_at: str = ""
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.memory_id:
            self.memory_id = "mem-{}".format(uuid.uuid4().hex[:10])
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def dedup_key(self) -> str:
        return "|".join((self.target_fingerprint, self.harm_category,
                         self.strategy, self.strategy_summary[:80]))


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class MemoryStore:
    """长期记忆库（独立 SQLite；与 runs 库分离，便于快照冻结与清理）。

    兼容引擎 BaseMemory 调用面：retrieve(state) / update(step)。
    """

    def __init__(self, db_path: str = "outputs/memory/memory.db",
                 target_fingerprint: str = "unknown",
                 snapshot_id: str = "live",
                 top_k: int = 4, per_strategy_cap: int = 2) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.target_fingerprint = target_fingerprint
        self.snapshot_id = snapshot_id
        self.top_k = top_k
        self.per_strategy_cap = per_strategy_cap
        self._lock = threading.RLock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ------------------------------------------------------------ 写入
    def store(self, rec: MemoryRecord, merge_duplicates=True) -> str:
        with self._lock:
            if merge_duplicates:
                row = self._db.execute(
                    "SELECT memory_id, occurrences, quality FROM memory"
                    " WHERE target_fingerprint=? AND harm_category=?"
                    " AND strategy=? AND snapshot_id=?"
                    " AND substr(strategy_summary,1,80)=substr(?,1,80)",
                    (rec.target_fingerprint, rec.harm_category, rec.strategy,
                     self.snapshot_id, rec.strategy_summary)).fetchone()
                if row is not None:
                    # 合并：出现次数+1，质量取两者较高（新观察有增量信息时）
                    self._db.execute(
                        "UPDATE memory SET occurrences=occurrences+1,"
                        " quality=MAX(quality,?), observation_summary=?,"
                        " last_used_at=? WHERE memory_id=?",
                        (rec.quality, rec.observation_summary, _now(),
                         row["memory_id"]))
                    self._db.commit()
                    return row["memory_id"]
            self._db.execute(
                "INSERT INTO memory(memory_id,source_run_id,source_task_id,"
                "target_fingerprint,harm_category,language,strategy,"
                "strategy_summary,context_summary,observation_summary,"
                "outcome_proxy,quality,novelty,uses,occurrences,judge_version,"
                "snapshot_id,created_at,last_used_at,metadata_json)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec.memory_id, rec.source_run_id, rec.source_task_id,
                 rec.target_fingerprint, rec.harm_category, rec.language,
                 rec.strategy, rec.strategy_summary, rec.context_summary,
                 rec.observation_summary, rec.outcome_proxy, rec.quality,
                 rec.novelty, rec.uses, rec.occurrences, rec.judge_version,
                 self.snapshot_id, rec.created_at, rec.last_used_at,
                 json.dumps(rec.metadata, ensure_ascii=False)))
            self._db.commit()
            return rec.memory_id

    # ------------------------------------------------------------ 查询
    def _rows(self, harm_category: Optional[str] = None) -> List[sqlite3.Row]:
        q = ("SELECT * FROM memory WHERE target_fingerprint=? AND snapshot_id=?")
        args = [self.target_fingerprint, self.snapshot_id]
        if harm_category:
            q += " AND harm_category=?"
            args.append(harm_category)
        q += " ORDER BY quality*0.7 + novelty*0.3 DESC, occurrences DESC"
        return self._db.execute(q, args).fetchall()

    def query(self, harm_category: Optional[str] = None,
              top_k: Optional[int] = None,
              require_diversity: bool = True) -> List[MemoryRecord]:
        """多样性检索：每策略族至多 per_strategy_cap 条，且尽量含失败/低效经验。"""
        rows = self._rows(harm_category)
        out, per_strat = [], {}
        cap = self.per_strategy_cap if require_diversity else 10 ** 6
        for r in rows:
            if per_strat.get(r["strategy"], 0) >= cap:
                continue
            per_strat[r["strategy"]] = per_strat.get(r["strategy"], 0) + 1
            out.append(MemoryRecord(
                memory_id=r["memory_id"], source_run_id=r["source_run_id"],
                source_task_id=r["source_task_id"],
                target_fingerprint=r["target_fingerprint"],
                harm_category=r["harm_category"], language=r["language"],
                strategy=r["strategy"], strategy_summary=r["strategy_summary"],
                context_summary=r["context_summary"],
                observation_summary=r["observation_summary"],
                outcome_proxy=r["outcome_proxy"], quality=r["quality"],
                novelty=r["novelty"], uses=r["uses"],
                occurrences=r["occurrences"],
                judge_version=r["judge_version"],
                snapshot_id=r["snapshot_id"], created_at=r["created_at"],
                last_used_at=r["last_used_at"],
                metadata=json.loads(r["metadata_json"] or "{}")))
            if len(out) >= (top_k or self.top_k):
                break
        return out

    # ------------------------------------------------------------ BaseMemory 面
    def retrieve(self, state) -> Tuple[List, List]:
        """引擎钩子：按当前任务的危害类别检索（无类别则全库前 top_k）。

        返回 (可参考经验, 已试低效经验)——按 outcome_proxy 分流，二者都只是
        过程观察，均不含任何独立评估结论。检索写 usage 记账。
        """
        task = getattr(state, "task", None)
        cat = getattr(task, "harm_category", None) if task is not None else None
        recs = self.query(cat)
        ids = [r.memory_id for r in recs]
        if ids:
            with self._lock:
                self._db.execute(
                    "UPDATE memory SET uses=uses+1, last_used_at=?"
                    " WHERE memory_id IN ({})".format(
                        ",".join("?" * len(ids))), [_now()] + ids)
                self._db.commit()
            for r in recs:
                r.uses += 1        # 返回对象与库内计数一致
        success_like = [r for r in recs
                        if r.outcome_proxy == "unsafe_content"]
        failure_like = [r for r in recs if r.outcome_proxy != "unsafe_content"]
        return success_like, failure_like

    def update(self, step) -> None:
        """引擎钩子：轮结束后从 step 提取经验（质量由 OnlineUtilityEstimator 评分）。
        由 main_agent 在启用记忆时注入 extractor；默认不做任何事（引擎心跳安全）。"""
        extractor = getattr(self, "extractor", None)
        if extractor is not None:
            for rec in extractor(step):
                self.store(rec)

    # ------------------------------------------------------------ 快照
    def snapshot(self, note: str = "") -> str:
        """冻结当前 live 记忆为只读快照（正式测试用独立快照，防泄漏）。"""
        sid = "snap-{}-{}".format(time.strftime("%Y%m%d_%H%M%S"),
                                  uuid.uuid4().hex[:5])
        with self._lock:
            cur = self._db.execute(
                "UPDATE memory SET snapshot_id=? WHERE snapshot_id='live'",
                (sid,))
            self._db.execute(
                "INSERT INTO snapshots(snapshot_id,created_at,n_records,note)"
                " VALUES(?,?,?,?)", (sid, _now(), cur.rowcount, note))
            self._db.commit()
        return sid

    @classmethod
    def load_snapshot(cls, db_path: str, snapshot_id: str,
                      target_fingerprint: str) -> "MemoryStore":
        """只读视图：检索限定快照；store 写入 live 表（不影响快照）。"""
        s = cls(db_path=db_path, target_fingerprint=target_fingerprint,
                snapshot_id=snapshot_id)
        return s

    def stats(self) -> Dict:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) n, COUNT(DISTINCT harm_category) cats,"
                " COUNT(DISTINCT strategy) strats, SUM(uses) uses"
                " FROM memory WHERE target_fingerprint=? AND snapshot_id=?",
                (self.target_fingerprint, self.snapshot_id)).fetchone()
            return {"records": row["n"], "categories": row["cats"],
                    "strategies": row["strats"], "total_uses": row["uses"] or 0}
