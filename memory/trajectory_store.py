# -*- coding: utf-8 -*-
"""轨迹存储：JSONL 保存 / 加载（设计文档 §26/§48：JSONL 可恢复完整 experiment）。"""
import json
import os
from typing import List

from core.schemas import AttackTrajectory


class TrajectoryStore:
    """一行一个 trajectory，追加写入。"""

    def __init__(self, output_dir: str = "outputs/trajectories") -> None:
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def save(self, trajectory: AttackTrajectory, name: str = "default") -> str:
        path = os.path.join(self.output_dir, "{}.jsonl".format(name))
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trajectory.to_dict(), ensure_ascii=False) + "\n")
        return path

    @staticmethod
    def load(path: str) -> List[AttackTrajectory]:
        trajs = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    trajs.append(AttackTrajectory.from_dict(json.loads(line)))
        return trajs
