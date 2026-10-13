# SafeLoop 轻量服务镜像：Web 工作台 + API + 历史回放（零 GPU）
# 适用：演示 / 报告查看 / 历史管理 / 黑盒 API 目标接入需另接 GPU 主机运行评估。
# 真实本地模型评估（红方/裁判/评审加载权重）请用源码方式部署（见 setup_env.md）。
FROM python:3.10-slim

WORKDIR /app
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi "uvicorn>=0.23"

COPY pyproject.toml setup_env.md ./
COPY apps ./apps
COPY safeloop ./safeloop
COPY core ./core
COPY engine ./engine
COPY agents ./agents
COPY targets ./targets
COPY evaluation ./evaluation
COPY memory ./memory
COPY scheduler ./scheduler
COPY feedback ./feedback
COPY experiments ./experiments
COPY utils ./utils
COPY prompts ./prompts
COPY configs ./configs
COPY data ./data
# 演示回放数据（载入示例数据 / 历史导入源）；用户运行数据经 volume 持久化
COPY outputs/evaluations ./outputs/evaluations
COPY outputs/trajectories ./outputs/trajectories

EXPOSE 8712
CMD ["python", "-m", "uvicorn", "apps.api.server:app", "--host", "0.0.0.0", "--port", "8712"]
