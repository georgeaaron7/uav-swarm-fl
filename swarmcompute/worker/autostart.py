"""Opt-in per-user startup only; disabling removes the owned registration."""

import os
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from ..config import worker_home


def configure(enable):
    system = platform.system()
    python = Path(sys.executable).resolve()
    home = worker_home()
    if system == "Linux":
        if not shutil.which("systemctl"):
            raise ValueError("systemd user services unavailable")
        path = Path.home() / ".config/systemd/user/swarmcompute.service"
        if enable:
            path.parent.mkdir(parents=True, exist_ok=True)
            # systemd percent substitutions must be escaped in all literal paths.
            quoted = str(python).replace("%", "%%").replace('"', '\\"')
            path.write_text(
                '[Unit]\nDescription=SwarmCompute voluntary worker\nAfter=network-online.target\n[Service]\nExecStart="'
                + quoted
                + '" -m swarmcompute start\nRestart=on-failure\nRestartSec=10\nEnvironment="SWARM_WORKER_HOME='
                + str(home).replace("%", "%%")
                + '"\n[Install]\nWantedBy=default.target\n'
            )
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            subprocess.run(
                ["systemctl", "--user", "enable", "--now", "swarmcompute.service"],
                check=True,
            )
        else:
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", "swarmcompute.service"],
                check=False,
            )
            path.unlink(missing_ok=True)
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        return str(path)
    if system == "Darwin":
        path = Path.home() / "Library/LaunchAgents/local.swarmcompute.worker.plist"
        if enable:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                plistlib.dumps(
                    {
                        "Label": "local.swarmcompute.worker",
                        "ProgramArguments": [
                            str(python),
                            "-m",
                            "swarmcompute",
                            "start",
                        ],
                        "EnvironmentVariables": {"SWARM_WORKER_HOME": str(home)},
                        "RunAtLoad": True,
                        "KeepAlive": {"SuccessfulExit": False},
                        "ThrottleInterval": 10,
                        "StandardOutPath": str(home / "startup.log"),
                        "StandardErrorPath": str(home / "startup-error.log"),
                    }
                )
            )
            subprocess.run(
                ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True
            )
        else:
            subprocess.run(
                ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)], check=False
            )
            path.unlink(missing_ok=True)
        return str(path)
    if system == "Windows":
        path = home / "autostart.xml"
        if enable:
            command = escape(str(python))
            working = escape(str(Path.cwd()))
            path.write_text(
                '<?xml version="1.0" encoding="UTF-16"?><Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers><Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals><Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><RestartOnFailure><Interval>PT1M</Interval><Count>10</Count></RestartOnFailure></Settings><Actions Context="Author"><Exec><Command>'
                + command
                + "</Command><Arguments>-m swarmcompute start</Arguments><WorkingDirectory>"
                + working
                + "</WorkingDirectory></Exec></Actions></Task>",
                encoding="utf-16",
            )
            subprocess.run(
                [
                    "schtasks",
                    "/Create",
                    "/TN",
                    "SwarmCompute Worker",
                    "/XML",
                    str(path),
                    "/F",
                ],
                check=True,
            )
        else:
            subprocess.run(
                ["schtasks", "/Delete", "/TN", "SwarmCompute Worker", "/F"], check=True
            )
            path.unlink(missing_ok=True)
        return "Task Scheduler: SwarmCompute Worker"
    raise ValueError("autostart unsupported on this platform")
