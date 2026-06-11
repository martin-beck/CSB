# Copyright (C) Huawei Technologies Co., Ltd. 2026. All rights reserved.
# SPDX-License-Identifier: MIT

from monitors.irq_softirq import IrqSoftirqStats


def test_parse_interrupts_totals_cpu_columns():
    data = IrqSoftirqStats.parse_interrupts(
        "           CPU0       CPU1\n"
        "  0:         10         20   IO-APIC   2-edge      timer\n"
        "RES:          1          2   Rescheduling interrupts\n"
    )

    assert data["irq_0"] == 30
    assert data["irq_res"] == 3
    assert data["irq_total"] == 33


def test_parse_softirqs_and_delta():
    data = IrqSoftirqStats.parse_softirqs(
        "                    CPU0       CPU1\n"
        "NET_RX:              10         5\n"
        "RCU:                  2         3\n"
    )

    assert data["softirq_net_rx"] == 15
    assert data["softirq_rcu"] == 5
    assert IrqSoftirqStats.delta({"softirq_total": 1}, data)["softirq_total_delta"] == 19
