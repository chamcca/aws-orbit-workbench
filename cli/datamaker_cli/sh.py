import logging
import subprocess
from typing import Iterable, Optional

from datamaker_cli.exceptions import FailedShellCommand

_logger: logging.Logger = logging.getLogger(__name__)


def _clean_up_stdout_line(line: bytes) -> str:
    line_str = line.decode("utf-8")
    return line_str[:-1] if line_str.endswith("\n") else line_str


def run_iterating(cmd: str, cwd: Optional[str] = None) -> Iterable[str]:
    p = subprocess.Popen(cmd.split(), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if p.stdout is None:
        return []
    while p.poll() is None:
        yield _clean_up_stdout_line(line=p.stdout.readline())
    if p.returncode != 0:
        raise FailedShellCommand(f"Exit code: {p.returncode}")


def run(cmd: str, cwd: Optional[str] = None, hide_cmd: bool = False) -> None:
    if hide_cmd is False:
        _logger.debug(f"+ {cmd}")
    for line in run_iterating(cmd=cmd, cwd=cwd):
        _logger.debug(line)