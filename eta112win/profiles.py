# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Desteklenen tahta profilleri.

Tablo, üst proje eta-112'den (Linux) BİREBİR taşınmıştır; donanım gerçekleri
(keystream, slot ofsetleri, NVRAM bankaları, çip) platformdan bağımsızdır, bu
yüzden Windows portunda da aynen geçerlidir. Yalnız `flash_mode` anlamı backend'e
göre yorumlanır (bkz. flash.py): "region" = tam çipin 0..RE aralığı; "ifd" =
Intel'de yalnız BIOS bölgesi (CHIPSEC flash descriptor'ından bölge tabanı bulunur).
"""


PROFILES = {
    ("14MB24A", "4.6.5"): {
        "model_name": "Faz 1 Vestel Intel (Siyah)",
        "label": "VESTEL 14MB24A / Intel Core i3-2310M, AMI Aptio",
        "keystream": bytes.fromhex("5b93b62611ba6c4dc7e022747d07d89a332e8ec1e95444e89f7bfa0e55a2b0350bc9665cc1ef1c83"),
        "slot_user": 0x00, "slot_super": 0x28, "slot_len": 40,
        "store_len": 81,
        "store_name": b"AMITSESetup",
        "pw_min": 3, "pw_max": 20,
        "chip": "MX25L3206E/MX25L3208E", "flash_mode": "ifd",
        "pwcheck_off": None, "pwcheck_opts": {1: "Setup", 2: "Always"},
        "setup_len": (545, 555),
        "active_store_end": 0x220000,
        "banks": [(0x200000, 0x210000), (0x210000, 0x220000)],
        "mac_ouis": {"00:09:DF": "Vestel Elektronik"},
        "verified": "Linux tarafında (eta-112) 2026-06-24 uçtan uca doğrulandı; "
                    "Windows portunda donanım testi YAPILMADI.",
    },
    ("14MB37C1", "L0.30"): {
        "model_name": "Faz 2 Vestel AMD (Gri)",
        "label": "VESTEL 14MB37C1 / AMD A10-5750M, AMI Aptio",
        "chip": "W25Q64BV/W25Q64CV/W25Q64FV",
        "keystream": bytes.fromhex("5b93b62611ba6c4dc7e022747d07d89a332e8ec1e95444e89f7bfa0e55a2"),
        "slot_user": 0x00, "slot_super": 0x1E, "slot_len": 30,
        "pw_min": 3, "pw_max": 15,
        "pwcheck_off": 0x14D, "pwcheck_opts": {1: "Setup", 2: "Always"},
        "store_len": 61, "setup_len": (330, 345), "flash_mode": "region",
        "active_store_end": 0x20000,
        "banks": [(0x0, 0x20000), (0x30000, 0x50000)],
        "mac_ouis": {"00:09:DF": "Vestel Elektronik"},
        "verified": "Linux tarafında (eta-112) 2026-06-19 doğrulandı; "
                    "Windows portunda donanım testi YAPILMADI.",
    },
    ("14MB57", "4.6.5"): {
        "model_name": "Faz 2 Vestel Intel (Gri)",
        "label": "VESTEL 14MB57 / Intel Core i3-4000M, AMI Aptio",
        "chip": None, "flash_mode": "ifd",
        "keystream": bytes.fromhex("5b93b62611ba6c4dc7e022747d07d89a332e8ec1e95444e89f7bfa0e55a2b0350bc9665cc1ef1c83"),
        "slot_user": 0x00, "slot_super": 0x28, "slot_len": 40,
        "store_len": 81,
        "pw_min": 3, "pw_max": 20,
        "pwcheck_off": 0x49F, "pwcheck_opts": {1: "Setup", 2: "Always"},
        "setup_len": (1330, 1340),
        "active_store_end": 0x440000,
        "banks": [(0x400000, 0x420000), (0x420000, 0x440000)],
        "mac_ouis": {"00:09:DF": "Vestel Elektronik"},
        "verified": "Linux tarafında (eta-112) 2026-06-22 doğrulandı; "
                    "Windows portunda donanım testi YAPILMADI.",
    },
}


def match_profile(d):
    """DMI/SMBIOS sözlüğünden (board + bios_version) profili bulur."""
    return PROFILES.get((d.get("board", ""), d.get("bios_version", "")))
