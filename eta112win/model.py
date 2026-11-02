# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Windows'ta anakart/BIOS model saptama.

Linux'taki dmidecode / /sys/class/dmi/id karşılığı. Önce SMBIOS tablosunu
GetSystemFirmwareTable('RSMB') ile ham okuyup Type 0 (BIOS) ve Type 2 (Baseboard)
yapılarını ayrıştırır (sürücüsüz, yönetici bile gerekmez); başarısızsa PowerShell
CIM (Win32_BaseBoard / Win32_BIOS) yedeğine düşer.
"""

import ctypes
import struct
import subprocess


_RSMB = int.from_bytes(b"RSMB", "big")  # 0x52534D42


def _raw_smbios():
    try:
        k = ctypes.windll.kernel32
    except Exception:
        return None
    k.GetSystemFirmwareTable.restype = ctypes.c_uint32
    k.GetSystemFirmwareTable.argtypes = [ctypes.c_uint32, ctypes.c_uint32,
                                         ctypes.c_void_p, ctypes.c_uint32]
    size = k.GetSystemFirmwareTable(_RSMB, 0, None, 0)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    got = k.GetSystemFirmwareTable(_RSMB, 0, buf, size)
    if not got:
        return None
    data = buf.raw[:got]
    # RawSMBIOSData: Used20CallingMethod, Major, Minor, DmiRevision, Length(DWORD), Data[]
    if len(data) < 8:
        return None
    length = struct.unpack("<I", data[4:8])[0]
    return data[8:8 + length]


def _iter_structs(tbl):
    """SMBIOS yapılarını (type, handle, formatted_bytes, strings[]) olarak dolaş."""
    i = 0
    n = len(tbl)
    while i + 4 <= n:
        stype = tbl[i]
        slen = tbl[i + 1]
        if slen < 4 or i + slen > n:
            break
        formatted = tbl[i:i + slen]
        # biçimli alandan sonra çift-NUL ile biten string tablosu
        j = i + slen
        strings = []
        start = j
        while j < n:
            if tbl[j] == 0:
                if j == start:          # boş string -> tablo sonu
                    j += 1
                    break
                strings.append(tbl[start:j].decode("latin-1", "replace"))
                start = j + 1
            j += 1
        if stype == 127:                # End-of-table
            break
        yield stype, formatted, strings
        i = j


def _smbios_str(strings, idx):
    return strings[idx - 1].strip() if 1 <= idx <= len(strings) else ""


def _from_smbios():
    tbl = _raw_smbios()
    if not tbl:
        return None
    out = {"board": "", "bios_version": "", "board_mfr": "", "bios_vendor": ""}
    seen0 = seen2 = False
    for stype, fmt, strings in _iter_structs(tbl):
        if stype == 0 and not seen0 and len(fmt) >= 6:       # BIOS Information
            out["bios_vendor"] = _smbios_str(strings, fmt[4])
            out["bios_version"] = _smbios_str(strings, fmt[5])
            seen0 = True
        elif stype == 2 and not seen2 and len(fmt) >= 6:     # Baseboard
            out["board_mfr"] = _smbios_str(strings, fmt[4])
            out["board"] = _smbios_str(strings, fmt[5])
            seen2 = True
    return out if (seen0 or seen2) else None


def _from_cim():
    """PowerShell CIM yedeği (SMBIOS ayrıştırması tutmazsa)."""
    ps = ("$b=Get-CimInstance Win32_BaseBoard; $i=Get-CimInstance Win32_BIOS;"
          "Write-Output $b.Product; Write-Output $b.Manufacturer;"
          "Write-Output $i.SMBIOSBIOSVersion; Write-Output $i.Manufacturer")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    lines = [l.strip() for l in (r.stdout or "").splitlines()]
    if len(lines) < 4:
        return None
    return {"board": lines[0], "board_mfr": lines[1],
            "bios_version": lines[2], "bios_vendor": lines[3]}


def dmi():
    """Model bilgisi sözlüğü: {board, bios_version, board_mfr, bios_vendor}."""
    return _from_smbios() or _from_cim() or {
        "board": "", "bios_version": "", "board_mfr": "", "bios_vendor": ""}
