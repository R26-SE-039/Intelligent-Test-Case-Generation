"""
Test execution module — runs generated test code via GitHub Actions or a
local Playwright subprocess, streams logs to the dashboard, persists results
+ artifacts + PDF report to the DB.
"""
from .log_broker import broker as log_broker

__all__ = ["log_broker"]
