# -*- coding: utf-8 -*-
"""SafeLoop Protocols（v1.0）：实验协议与验证器入口。"""
from core.protocol import (ExperimentProtocol, FEEDBACK_NONE, FEEDBACK_SCORE,
                           FEEDBACK_STRUCTURED, STRATEGY_ORDER)  # noqa: F401
from core.protocol_validator import ProtocolValidator, ProtocolViolation  # noqa: F401
