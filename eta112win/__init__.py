# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — eta-112'nin Windows portu (BIOS/EEPROM işlemleri)
# Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""eta-112-win: Pardus ETAP akıllı tahtalar için Windows BIOS/EEPROM aracı.

Orijinal eta-112 (Linux) aracının firmware/EEPROM işlevlerinin Windows portu.
Platform-bağımsız çözümleme mantığı (profiller, keystream, NVAR tarama, MSDM,
MAC doğrulama) üst projeden birebir taşınmıştır; donanım erişim katmanı Windows'a
özgüdür (CHIPSEC SPI + Win32 firmware API'leri).
"""

VERSION = "0.1.0"
