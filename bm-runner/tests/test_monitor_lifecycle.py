# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from bm_executer import Executer


class RecordingMonitor:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def stop(self):
        self.events.append(self.name)


def test_monitors_stop_in_reverse_start_order():
    events = []
    executer = Executer.__new__(Executer)
    executer.monitors = [
        RecordingMonitor("dependency", events),
        RecordingMonitor("collector-a", events),
        RecordingMonitor("collector-b", events),
    ]

    executer._Executer__stop_monitors()

    assert events == ["collector-b", "collector-a", "dependency"]
