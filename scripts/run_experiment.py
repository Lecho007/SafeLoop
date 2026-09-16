# -*- coding: utf-8 -*-
"""Stage 1 四条件实验（C0/C1/C2/C3，主比较 C1 vs C3）。

用法：python scripts/run_experiment.py [configs/stage1.yaml]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments.stage1 import main


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "configs/stage1.yaml")
