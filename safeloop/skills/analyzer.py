# -*- coding: utf-8 -*-
"""AI 报告分析技能(本地 Qwen3-4B · NF4)。

设计边界(与工程红线一致):
  - AI 分析是"解读"不是"裁决":只解释独立评审已产出的数字,
    永不改变评估结论;报告页 UI 须标注"仅供参考";
  - 不进在线闭环:仅在 run 终态后按需触发,不反馈红方/调度/记忆;
  - 输入最小化:只发聚合统计、类别分布、代表案例摘要与多轮暴露案例
    的任务号/类别/触发轮,不发攻击 prompt 与回答全文;
  - 结果缓存:outputs/reports/{run_id}_ai_analysis.json,同 run 不重复推理。

模型:weights/analyzer/Qwen3-4B,NF4 量化加载(约 2.6GB 显存,8GB 卡可单驻留),
Qwen3 chat template 关闭思考模式;生成失败抛 AnalyzerError,由 API 层转 5xx。
"""
import json
import logging
import os
import threading
import time

from utils.io import load_yaml

logger = logging.getLogger("safeloop.analyzer")

DEFAULT_MODEL_PATH = "weights/analyzer/Qwen3-4B"
DEFAULT_PROMPT = "prompts/analyzer/analysis_v1.yaml"


class AnalyzerError(RuntimeError):
    pass


def summarize_for_prompt(report: dict, turning_cases=None) -> dict:
    """报告 dict → 送入 prompt 的最小摘要(纯函数,单测覆盖)。

    turning_cases: [{task_id, category, first_round}] 首轮安全、后续轮才
    触发风险的案例(由调用方从轨迹提取),是最有解读价值的素材。
    """
    ov = report.get("overview") or {}
    ul = (report.get("metrics") or {}).get("user_layer") or {}
    data = {
        "risk_tasks": ov.get("risk_tasks"),
        "total_tasks": ov.get("total_tasks"),
        "mode": ov.get("mode"),
        "target": ov.get("target"),
        "risk_rate": ul.get("asr_at_budget"),
        "auc_b": ul.get("auc_b"),
        "mean_first_trigger_round": ul.get("mean_ctts"),
        "risk_distribution": report.get("risk_distribution") or {},
        "representative_cases": [
            {"task_id": c.get("task_id"), "category": c.get("category"),
             "note": c.get("why_representative")}
            for c in (report.get("representative_cases") or [])[:5]],
    }
    comp = report.get("comparison")
    if comp:
        data["comparison"] = {
            k: comp.get(k, {}).get("asr_at_budget")
            for k in ("standard", "guided") if isinstance(comp.get(k), dict)}
    if report.get("adaptive"):
        a = report["adaptive"]
        data["adaptive"] = {k: a.get(k) for k in (
            "total_budget", "queries_used", "distinct_risky_tasks",
            "yield", "under_tested_tasks")}
    if turning_cases:
        data["multi_round_revealed_cases"] = turning_cases[:8]
    return data


class AnalyzerSkill:
    name = "report_analyzer"
    version = "analyzer-1.0"

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH,
                 prompt_path: str = DEFAULT_PROMPT,
                 max_new_tokens: int = 900,
                 device: str = "cuda") -> None:
        self.model_path = model_path
        self.prompt_path = prompt_path
        self.max_new_tokens = max_new_tokens
        self.device = device
        self._model = None
        self._tokenizer = None
        self._lock = threading.Lock()   # 单 GPU:防并发分析

    # ------------------------------------------------------------ prompt
    def build_messages(self, report: dict, turning_cases=None):
        tpl = load_yaml(self.prompt_path)
        data = summarize_for_prompt(report, turning_cases)
        return [
            {"role": "system", "content": tpl["system"].strip()},
            {"role": "user", "content": tpl["user"]
                .replace("{report_json}", json.dumps(data, ensure_ascii=False,
                                                     indent=1))},
        ]

    # ------------------------------------------------------------ 模型
    def _load(self):
        if self._model is not None:
            return
        if not os.path.isdir(self.model_path):
            raise AnalyzerError(
                "分析器权重不存在: {}(先执行 hf download Qwen/Qwen3-4B "
                "--local-dir weights/analyzer/Qwen3-4B)".format(self.model_path))
        try:
            import torch
            from transformers import (AutoModelForCausalLM, AutoTokenizer,
                                      BitsAndBytesConfig)
        except ImportError as e:
            raise AnalyzerError("分析器依赖缺失(需要 GPU 环境): {}".format(e))
        if not torch.cuda.is_available():
            raise AnalyzerError("分析器需要 CUDA(当前环境无可用 GPU)")
        logger.info("loading analyzer model %s (nf4)", self.model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16),
            device_map=self.device)

    def analyze(self, run_id: str, report: dict, turning_cases=None) -> dict:
        """生成分析并写缓存(同步,本地推理约 10-40s)。"""
        with self._lock:
            self._load()
            messages = self.build_messages(report, turning_cases)
            try:
                text = self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True,
                    enable_thinking=False)
            except TypeError:   # 模板不支持 enable_thinking 的回退
                text = self._tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True)
            import torch
            inputs = self._tokenizer(text, return_tensors="pt").to(self.device)
            logger.info("analyzing report for %s ...", run_id)
            t0 = time.time()
            with torch.no_grad():
                out = self._model.generate(
                    **inputs, max_new_tokens=self.max_new_tokens,
                    do_sample=True, temperature=0.5, top_p=0.9)
            gen = out[0][inputs["input_ids"].shape[1]:]
            result_text = self._tokenizer.decode(
                gen, skip_special_tokens=True).strip()
            if not result_text:
                raise AnalyzerError("分析器输出为空")
            result = {"version": self.version, "ts": time.time(),
                      "model": "Qwen3-4B(NF4)",
                      "elapsed_s": round(time.time() - t0, 1),
                      "text": result_text}
            self._save_cache(run_id, result)
            return result

    # ------------------------------------------------------------ 缓存
    @staticmethod
    def cache_path(run_id: str) -> str:
        return os.path.join("outputs", "reports",
                            "{}_ai_analysis.json".format(run_id))

    @classmethod
    def load_cache(cls, run_id: str):
        p = cls.cache_path(run_id)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                return None
        return None

    def _save_cache(self, run_id: str, result: dict) -> None:
        os.makedirs(os.path.dirname(self.cache_path(run_id)), exist_ok=True)
        with open(self.cache_path(run_id), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


def extract_turning_cases(trajectories) -> list:
    """从轨迹提取「首轮安全、后续轮才触发」的案例(送入 prompt 的关键素材)。

    兼容两种形态:后端轨迹对象(task 嵌套字段)与 API 扁平 dict(task_id 平铺)。
    """
    def _field(t, dict_keys, obj_path):
        if isinstance(t, dict):
            for k in dict_keys:
                if t.get(k):
                    return t.get(k)
            return ""
        obj = t
        for attr in obj_path:
            obj = getattr(obj, attr, None)
            if obj is None:
                return ""
        return obj or ""

    out = []
    for t in trajectories or []:
        steps = (t.get("steps") if isinstance(t, dict) else getattr(t, "steps", None)) or []
        ok = (lambda s: bool((s.get("external_evaluation") or {}).get("success"))
              if isinstance(s, dict)
              else bool(getattr(getattr(s, "external_evaluation", None),
                                "success", False)))
        if not steps or ok(steps[0]):
            continue
        first = next((i + 1 for i, s in enumerate(steps) if ok(s)), None)
        if first:
            out.append({
                "task_id": _field(t, ("task_id",), ("task", "task_id")),
                "category": _field(t, ("category", "harm_category"),
                                   ("task", "harm_category")),
                "first_round": first})
    out.sort(key=lambda x: x["first_round"], reverse=True)
    return out
