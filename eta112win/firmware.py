# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""Sürücüsüz Win32 firmware erişimi.

- read_acpi_table('MSDM'): ACPI MSDM tablosunu GetSystemFirmwareTable ile ham okur
  (Windows ürün anahtarını OKUMAK için — sürücü gerekmez, yalnız yönetici).
- get_uefi_var / set_uefi_var: UEFI çalışan sistemlerde firmware NVRAM değişkeni
  okuma/yazma (Get/SetFirmwareEnvironmentVariableW, SeSystemEnvironmentPrivilege).
  ETAP tahtaları çoğunlukla legacy (CSM) başlatılır; o durumda bu API başarısız olur
  ve BIOS parola erişimi için SPI flash (bkz. flash.py) gerekir.
"""

import ctypes
from ctypes import wintypes


_ACPI_PROVIDERS = (int.from_bytes(b"ACPI", "big"), int.from_bytes(b"ACPI", "little"))


def _table_id_candidates(sig4):
    b = sig4.encode("ascii")
    return (int.from_bytes(b, "little"), int.from_bytes(b, "big"))


def read_acpi_table(sig4="MSDM"):
    """ACPI tablosunu (başlık dahil) ham bayt olarak döner, yoksa None.
    Dönen baytlar tablo imzasıyla (ör. b'MSDM') başlar."""
    try:
        k = ctypes.windll.kernel32
    except Exception:
        return None
    k.GetSystemFirmwareTable.restype = ctypes.c_uint32
    k.GetSystemFirmwareTable.argtypes = [ctypes.c_uint32, ctypes.c_uint32,
                                         ctypes.c_void_p, ctypes.c_uint32]
    want = sig4.encode("ascii")
    for prov in _ACPI_PROVIDERS:
        for tid in _table_id_candidates(sig4):
            size = k.GetSystemFirmwareTable(prov, tid, None, 0)
            if not size:
                continue
            buf = ctypes.create_string_buffer(size)
            got = k.GetSystemFirmwareTable(prov, tid, buf, size)
            if got and buf.raw[:4] == want:
                return buf.raw[:got]
    return None


def has_acpi_table(sig4):
    """EnumSystemFirmwareTables ile tablo var mı diye bakar (SLIC tespiti için)."""
    try:
        k = ctypes.windll.kernel32
    except Exception:
        return False
    k.EnumSystemFirmwareTables.restype = ctypes.c_uint32
    want = sig4.encode("ascii")
    for prov in _ACPI_PROVIDERS:
        size = k.EnumSystemFirmwareTables(prov, None, 0)
        if not size:
            continue
        buf = ctypes.create_string_buffer(size)
        if not k.EnumSystemFirmwareTables(prov, buf, size):
            continue
        raw = buf.raw[:size]
        for i in range(0, len(raw) - 3, 4):
            if raw[i:i + 4] == want:
                return True
    return False


# ---------- UEFI değişkeni (yalnız UEFI başlatmada) ----------
def _enable_system_env_privilege():
    """SeSystemEnvironmentPrivilege'i etkinleştir (UEFI değişkeni için gerekir)."""
    try:
        adv = ctypes.windll.advapi32
        k = ctypes.windll.kernel32

        class LUID(ctypes.Structure):
            _fields_ = [("Low", wintypes.DWORD), ("High", wintypes.LONG)]

        class LUID_AND_ATTR(ctypes.Structure):
            _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

        class TOKEN_PRIVILEGES(ctypes.Structure):
            _fields_ = [("Count", wintypes.DWORD), ("Priv", LUID_AND_ATTR)]

        h = wintypes.HANDLE()
        TOKEN_ADJUST_PRIVILEGES = 0x20
        TOKEN_QUERY = 0x8
        if not adv.OpenProcessToken(k.GetCurrentProcess(),
                                    TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
                                    ctypes.byref(h)):
            return False
        luid = LUID()
        if not adv.LookupPrivilegeValueW(None, "SeSystemEnvironmentPrivilege",
                                         ctypes.byref(luid)):
            return False
        tp = TOKEN_PRIVILEGES()
        tp.Count = 1
        tp.Priv.Luid = luid
        tp.Priv.Attributes = 0x2  # SE_PRIVILEGE_ENABLED
        adv.AdjustTokenPrivileges(h, False, ctypes.byref(tp), 0, None, None)
        return ctypes.get_last_error() == 0
    except Exception:
        return False


def get_uefi_var(name, guid, maxlen=65536):
    """UEFI firmware değişkenini okur (bytes) ya da None. guid: '{...}' biçimi."""
    try:
        k = ctypes.windll.kernel32
        k.GetFirmwareEnvironmentVariableW.restype = wintypes.DWORD
        k.GetFirmwareEnvironmentVariableW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
                                                      ctypes.c_void_p, wintypes.DWORD]
        _enable_system_env_privilege()
        buf = ctypes.create_string_buffer(maxlen)
        n = k.GetFirmwareEnvironmentVariableW(name, guid, buf, maxlen)
        return buf.raw[:n] if n else None
    except Exception:
        return None


def set_uefi_var(name, guid, data):
    """UEFI firmware değişkenine yazar. Döner bool (başarı)."""
    try:
        k = ctypes.windll.kernel32
        k.SetFirmwareEnvironmentVariableW.restype = wintypes.BOOL
        k.SetFirmwareEnvironmentVariableW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR,
                                                      ctypes.c_void_p, wintypes.DWORD]
        _enable_system_env_privilege()
        return bool(k.SetFirmwareEnvironmentVariableW(name, guid, data, len(data)))
    except Exception:
        return False
