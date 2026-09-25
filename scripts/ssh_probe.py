#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSH 探针：远程执行命令（密码登录）。用法：python3 ssh_probe.py "cmd" """
import sys
import pexpect

HOST = "connect.bjb1.seetacloud.com"
PORT = "31515"
PASSWORD = "oUge0O0wowB1"


def run(cmd: str, timeout: int = 90) -> str:
    child = pexpect.spawn(
        "ssh -p {port} -o StrictHostKeyChecking=no root@{host} -- bash -s"
        .format(port=PORT, host=HOST),
        encoding="utf-8", timeout=timeout)
    i = child.expect(["[Pp]assword:", "\\$ "], timeout=30)
    if i == 0:
        child.sendline(PASSWORD)
    child.sendline(cmd)
    child.sendline("exit")
    child.expect(pexpect.EOF)
    return child.before or ""


if __name__ == "__main__":
    print(run(sys.argv[1]))
