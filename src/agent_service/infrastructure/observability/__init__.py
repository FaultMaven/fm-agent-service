"""
FaultMaven Agent Service - Observability Infrastructure

Provides distributed tracing and monitoring using Opik.
"""

from .tracing import OpikTracer, get_tracer

__all__ = [
    'OpikTracer',
    'get_tracer',
]
