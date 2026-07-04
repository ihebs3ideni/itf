"""ITF plugins with contract-based coordination."""

from score.itf.plugins.mock_target import MockTargetPlugin
from score.itf.plugins.mock_ssh import MockSshPlugin
from score.itf.plugins.coredump_handler import CoredumpHandlerPlugin
from score.itf.plugins.oracle import OraclePlugin
from score.itf.plugins.log_capture import LogCapturePlugin
from score.itf.plugins.json_report import JsonReportPlugin

__all__ = [
    "MockTargetPlugin",
    "MockSshPlugin",
    "CoredumpHandlerPlugin",
    "OraclePlugin",
    "LogCapturePlugin",
    "JsonReportPlugin",
]
