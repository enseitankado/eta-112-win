#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — eta-112'nin Windows portu (BIOS/EEPROM işlemleri)
# Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Giriş noktası. Çalıştırma (yönetici CMD/PowerShell):

    python eta-112-win.py
    python eta-112-win.py bios read
    python eta-112-win.py wkey read
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eta112win.cli import entry  # noqa: E402

if __name__ == "__main__":
    entry()
