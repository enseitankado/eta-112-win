# SPDX-License-Identifier: GPL-3.0-or-later
# eta-112-win — Copyright (C) 2026 Özgür Koca <https://ozgurkoca.com>
"""BIOS yönetici/kullanıcı parolası: oku · ayarla · temizle · bilgi · kalibrasyon.

Çözümleme mantığı codec.py'den (eta-112 ile birebir) gelir; flash erişimi Windows'ta
flash.FlashSession (CHIPSEC) üzerinden yapılır. JSON sözleşmesi Linux portuyla aynıdır.
"""

import struct

from . import ui, codec, flash
from .ui import (B, R, G, Y, Cy, D, OK, WARN, ERR, emit)
from .model import dmi
from .profiles import match_profile, PROFILES

_JSON = lambda: ui.JSON


def validate_pw(s, pmin, pmax):
    u = (s or "").upper()
    if any(not ("A" <= c <= "Z" or "0" <= c <= "9") for c in u):
        return None, "yalnız A-Z ve 0-9 kullanılabilir"
    if not (pmin <= len(u) <= pmax):
        return None, f"uzunluk {pmin}-{pmax} olmalı"
    return u, None


# ===================== model / kaynak =====================
def need_profile():
    d = dmi()
    prof = match_profile(d)
    if _JSON():
        return prof, d
    if prof and prof.get("model_name"):
        print(f"  Model: {G(prof['model_name'])}")
    print(f"  Kart : {Cy(d.get('board_mfr', '?'))} {Cy(d.get('board', '?'))}")
    print(f"  BIOS : {d.get('bios_vendor', '?')} sürüm {Cy(d.get('bios_version', '?'))}")
    if prof:
        print(f"  Durum: {OK} {G('DESTEKLENİYOR')}  {D('(' + prof['label'] + ')')}")
    else:
        same = [k for k in PROFILES if k[0] == d.get("board")]
        if same:
            print(f"  Durum: {WARN} {Y('AYNI KART, FARKLI BIOS SÜRÜMÜ')} (destekli: {[k[1] for k in same]})")
            print(D("         keystream/offset farklı olabilir -> 'calibrate' ile doğrula."))
        else:
            print(f"  Durum: {ERR} {R('DESTEKLENMİYOR')} -> işlem yapılmaz.")
    return prof, d


def load_source(prof, dumppath):
    """(ents, setup, src) döner. ents None ise src hata metnidir."""
    if dumppath:
        with open(dumppath, "rb") as f:
            data = f.read()
        return (*codec.scan(data, prof), "dump")
    if not ui.is_admin():
        return None, None, "Bu işlem için yönetici (Administrator) gerekli."
    from . import preflight
    cok, cmsg = preflight.ensure_chipsec(interactive=not ui.JSON)
    if not cok:
        return None, None, cmsg
    sess = flash.FlashSession(prof)
    try:
        data = sess.read_region()
    except flash.FlashError as e:
        return None, None, str(e)
    finally:
        sess.close()
    return (*codec.scan(data, prof), "flash")


# ===================== oku / bilgi / kalibrasyon =====================
def cmd_info(a):
    prof, d = need_profile()
    if _JSON():
        if not prof:
            return emit({"ok": False, "supported": False, "board": d.get("board"),
                         "bios": d.get("bios_version"), "error": "desteklenmeyen model/sürüm"}, 1)
        return emit({"ok": True, "supported": True, "model": prof.get("model_name"),
                     "board": d.get("board"), "bios": d.get("bios_version"), "chip": prof["chip"],
                     "pw_min": prof["pw_min"], "pw_max": prof["pw_max"]})
    if prof:
        print(f"  Parola: {prof['pw_min']}-{prof['pw_max']} karakter, BÜYÜK harf")
        print(f"  Çip   : {prof['chip']}")
    return 0 if prof else 1


def cmd_read(a):
    prof, d = need_profile()
    if not prof:
        return emit({"ok": False, "supported": False, "error": "desteklenmeyen model/sürüm"}, 1) if _JSON() else 1
    ents, setup, src = load_source(prof, getattr(a, "dump", None))
    if ents is None:
        if _JSON():
            return emit({"ok": False, "error": str(src)}, 1)
        print(R("  " + str(src)))
        return 1
    ents = codec.pw_filter(ents, prof)
    ks = prof["keystream"]
    su, sp, sl = prof["slot_user"], prof["slot_super"], prof["slot_len"]
    cur = codec.resolve_current(ents, prof["banks"])
    du = codec.decode(cur[su:su + sl], ks) if cur else None
    ds = codec.decode(cur[sp:sp + sl], ks) if cur else None
    prev = []
    seen = set()
    for e in sorted(ents, key=lambda e: e["off"]):
        if e["blob"] == cur:
            continue
        u = codec.decode(e["blob"][su:su + sl], ks)
        s = codec.decode(e["blob"][sp:sp + sl], ks)
        if not (u or s):
            continue
        yon = codec.trq(s) if s else None
        kul = codec.trq(u) if u else None
        key = (yon or "-", kul or "-")
        if key in seen:
            continue
        seen.add(key)
        prev.append((yon, kul))
    prot = None
    pco = prof.get("pwcheck_off")
    if pco is not None and setup and len(setup) > pco and setup[pco] in (1, 2):
        prot = "always" if setup[pco] == 2 else "setup"
    elif pco is None:
        prot = "always" if du else ("setup" if ds else None)
    if _JSON():
        return emit({"ok": True, "supported": True, "model": prof.get("model_name"),
                     "board": d.get("board"), "bios": d.get("bios_version"),
                     "supervisor": codec.trq(ds) if ds else None,
                     "user": codec.trq(du) if du else None,
                     "previous": [{"supervisor": y, "user": k} for (y, k) in prev],
                     "protection": prot})
    print(B("\nGüncel parolalar"))

    def show(lbl, raw):
        if raw is None:
            print(f"  {lbl:<10}: {D('(parola yok)')}")
        elif codec.is_clean(raw):
            print(f"  {lbl:<10}: {G(codec.trq(raw))}")
        else:
            print(f"  {lbl:<10}: {R(codec.trq(raw))}  {WARN} {Y('okunamadı (model/sürüm uyumsuz)')}")
    show("Yönetici", ds)
    show("Kullanıcı", du)
    if prev:
        print(B("\nÖnceki parolalar"))
        for i, (yon, kul) in enumerate(prev, 1):
            print(f"  {D(str(i) + '.'):<3} Yönetici: {(yon or '-'):<14} Kullanıcı: {(kul or '-')}")
    if prof.get("pwcheck_off") is None:
        kor = (Y("her açılışta sorulur") + D("  (Kullanıcı parolası ayarlı)")) if prot == "always" \
            else (G("yalnızca BIOS ayarlarına girerken sorulur") + D("  (yalnız Yönetici ayarlı)")) if prot == "setup" \
            else D("parola ayarlı değil")
        kor += D("  — bu modelde ayrı 'ne zaman sorulsun' ayarı yoktur")
    else:
        kor = (Y("her açılışta sorulur") if prot == "always"
               else G("yalnızca BIOS ayarlarına girerken sorulur")) if prot else D("okunamadı")
    print(f"\n  {D('Koruma:')} {kor}")
    return 0


def cmd_calibrate(a):
    prof, d = need_profile()
    pp = prof or PROFILES[next(iter(PROFILES))]
    ents, _s, src = load_source(pp, getattr(a, "dump", None))
    if ents is None:
        return emit({"ok": False, "error": str(src)}, 1) if _JSON() else (print(R("  " + str(src))) or 1)
    ents = codec.pw_filter(ents, pp)
    off = pp["slot_user"] if a.slot in ("user", "kullanici") else pp["slot_super"]
    sl = pp["slot_len"]
    blob = codec.resolve_current(ents, pp["banks"])
    cur = blob[off:off + sl] if blob else None
    if not cur or cur == b"\x00" * sl:
        if _JSON():
            return emit({"ok": False, "error": "slot boş; önce BIOS'tan parola ayarlayın"}, 1)
        print(R(f"  {a.slot} slotu boş. Önce BIOS'tan bu parolayı ayarlayın."))
        return 1
    b = codec.to_bios(a.password, pp["pw_max"])
    b = (b.encode("utf-16-le") + b"\x00" * sl)[:sl]
    derived = bytes(x ^ y for x, y in zip(cur, b))
    matches = bool(prof and derived == prof["keystream"])
    if _JSON():
        return emit({"ok": True, "keystream": derived.hex(), "matches": matches})
    print(B("\n=== KALİBRASYON ==="))
    print(f"  türetilen keystream: {G(derived.hex())}")
    if matches:
        print(f"  {OK} {G('Profil ile AYNI')} -> doğru.")
    elif prof:
        print(f"  {WARN} {Y('Profil keystreaminden FARKLI')} -> yeni profil olarak ekleyin.")
    return 0


# ===================== düzenleme / yazma =====================
def _edit_image(data, prof, edits):
    """Yalnız AKTİF parola girişini düzenler (resolve_current_entry). Eskiden bankadaki
    TÜM girişler düzenleniyordu; bu, 14MB57 gibi çok sayıda eski AMITSESetup girişi
    biriken kartlarda ~256 KiB'lik gereksiz/riskli bir yazma span'ine yol açıyordu.
    Aktif giriş tek sektördedir; BIOS parolayı zaten o girişten okur."""
    data = bytearray(data)
    changes = []
    ents = codec.pw_filter(codec.nvar_scan(data, prof.get("store_len", 61)), prof)
    e = codec.resolve_current_entry(ents, prof["banks"])
    if e is None or not any(lo <= e["off"] < hi for (lo, hi) in prof["banks"]):
        return bytes(data), changes
    for off, val in edits:
        a = e["data_off"] + off
        old = bytes(data[a:a + prof["slot_len"]])
        if old != val:
            data[a:a + prof["slot_len"]] = val
            changes.append((a, old, val))
    return bytes(data), changes


def _edit_setup_pwcheck(data, prof, value):
    data = bytearray(data)
    changes = []
    off = prof["pwcheck_off"]
    n = len(data)
    NV = b"NVAR"
    slo, shi = prof.get("setup_len", (330, 345))
    i = data.find(NV)
    while i != -1 and i < n - 10:
        size = struct.unpack("<H", data[i + 4:i + 6])[0]
        if 8 < size < 0x800 and i + size <= n:
            flags = data[i + 9]
            if flags & 0x02:
                end = data.find(b"\x00", i + 11)
                doff = (end + 1) - i if end != -1 else 10
            else:
                doff = 10
            if slo <= size - doff <= shi and any(lo <= i < hi for (lo, hi) in prof["banks"]):
                a = i + doff + off
                if i < a < i + size and data[a] != value:
                    changes.append((a, data[a], value))
                    data[a] = value
            i = data.find(NV, i + size)
        else:
            i = data.find(NV, i + 1)
    return bytes(data), changes


def _write_flow(prof, edits, pwcheck=None):
    """Oku + düzenle + yaz -> geri-oku doğrula. Döner {ok,changed,error,verified}."""
    if not ui.is_admin():
        return {"ok": False, "changed": False, "error": "yönetici gerekli"}
    from . import preflight
    cok, cmsg = preflight.ensure_chipsec(interactive=not ui.JSON)
    if not cok:
        return {"ok": False, "changed": False, "error": cmsg}
    sl = prof["slot_len"]
    sess = flash.FlashSession(prof)
    try:
        try:
            cur = sess.read_region()
        except flash.FlashError as e:
            return {"ok": False, "changed": False, "error": str(e)}
        if prof.get("store_name"):
            live = [e for e in codec.pw_filter(codec.nvar_scan(cur, prof.get("store_len", 61)), prof)
                    if any(lo <= e["off"] < hi for (lo, hi) in prof["banks"])]
            if not live:
                return {"ok": False, "changed": False, "error": "no_live_store"}
        new, changes = _edit_image(cur, prof, edits)
        if pwcheck is not None:
            new, pchanges = _edit_setup_pwcheck(new, prof, pwcheck)
            changes = changes + pchanges
        if not changes:
            return {"ok": True, "changed": False, "error": None, "verified": True}
        ok, msg = sess.write_region(new)
        if not ok:
            return {"ok": False, "changed": False, "error": "yazma başarısız: " + msg}
        verified = "doğrulan" in msg  # "yazıldı ve doğrulandı"
        # içerik düzeyinde ikinci doğrulama (slot/pwcheck değerleri)
        try:
            rb = sess.read_region()
            edok = True
            if edits:
                b = codec.resolve_current(codec.pw_filter(codec.nvar_scan(rb, prof.get("store_len", 61)), prof), prof["banks"])
                edok = bool(b) and all(b[off:off + sl] == val for off, val in edits)
            pwok = True
            if pwcheck is not None:
                sp = codec.nvar_setup_payload(rb, prof["active_store_end"], prof.get("setup_len", (330, 345)))
                pwok = bool(sp) and prof.get("pwcheck_off") is not None and \
                    len(sp) > prof["pwcheck_off"] and sp[prof["pwcheck_off"]] == pwcheck
            verified = verified and edok and pwok
        except flash.FlashError:
            verified = False
        return {"ok": True, "changed": True, "error": None, "verified": verified}
    finally:
        sess.close()


def _dryrun_write(prof, edits, pwcheck, dumppath, outpath):
    """Donanıma DOKUNMADAN: kaynak dump imajını düzenleyip sonucu outpath'e yazar.
    Yönetici/CHIPSEC gerektirmez; brick riski yoktur. Yazma mantığını doğrulamak
    ve harici flashlama için düzenlenmiş ROM üretmek içindir. Döner _write_flow ile
    aynı biçimde {ok,changed,error,verified,out}."""
    if not dumppath:
        return {"ok": False, "changed": False,
                "error": "dry-run için --dump (kaynak imaj) gerekli", "out": None}
    try:
        with open(dumppath, "rb") as f:
            data = f.read()
    except OSError as e:
        return {"ok": False, "changed": False, "error": "dump okunamadı: %s" % e, "out": None}
    sl = prof["slot_len"]
    new, changes = _edit_image(data, prof, edits)
    if pwcheck is not None:
        new, pchanges = _edit_setup_pwcheck(new, prof, pwcheck)
        changes = changes + pchanges
    if not changes:
        return {"ok": True, "changed": False, "error": None, "verified": True, "out": None}
    try:
        with open(outpath, "wb") as f:
            f.write(new)
    except OSError as e:
        return {"ok": False, "changed": False, "error": "çıktı yazılamadı: %s" % e, "out": None}
    # içerik doğrulaması: yeni imajı yeniden tarayıp beklenen değerleri kontrol et
    verified = len(new) == len(data)
    if edits:
        b = codec.resolve_current(
            codec.pw_filter(codec.nvar_scan(new, prof.get("store_len", 61)), prof),
            prof["banks"])
        verified = verified and bool(b) and all(b[off:off + sl] == val for off, val in edits)
    if pwcheck is not None:
        sp = codec.nvar_setup_payload(new, prof["active_store_end"],
                                      prof.get("setup_len", (330, 345)))
        pco = prof.get("pwcheck_off")
        verified = verified and bool(sp) and pco is not None and \
            len(sp) > pco and sp[pco] == pwcheck
    return {"ok": True, "changed": True, "error": None, "verified": verified, "out": outpath}


def _write_result_print(res):
    if res.get("out"):
        if not res.get("verified", True):
            print(f"  {WARN} {Y('Düzenlenmiş imaj yazıldı ama içerik doğrulaması tutmadı:')} {res['out']}")
        else:
            print(f"  {OK} {G('Düzenlenmiş imaj yazıldı ve doğrulandı:')} {res['out']}")
            print(D("  (donanıma dokunulmadı — dry-run). Harici flashlama/inceleme için kullanılabilir."))
        return
    if res.get("changed") is False and res.get("error") is None and "out" in res:
        print(Y("  Kaynak imajda parolalar zaten istenen durumda; dosya yazılmadı."))
        return
    if res["error"] == "yönetici gerekli":
        print(R("  Bunun için yönetici (Administrator) gerekli."))
    elif res["error"] == "no_live_store":
        print(Y("  BIOS'ta henüz hiç parola kurulmamış (AMITSESetup değişkeni oluşmamış)."))
        print(D("  Önce BIOS setup'a girip herhangi bir parola ayarlayıp kaydedin (F10);"))
        print(D("  değişken oluştuktan sonra bu araçla oku/ayarla/temizle tam çalışır."))
    elif res["error"]:
        print(R(f"  İşlem başarısız: {res['error']}."))
    elif not res["changed"]:
        print(Y("  Parolalar zaten istenen durumda."))
    elif not res.get("verified", True):
        print(f"  {WARN} {Y('Yazıldı ama doğrulama tutmadı.')}")
    else:
        print(f"  {OK} {G('Tamam.')} {Y('Etkili olması için bilgisayarı yeniden başlatın.')}")


def cmd_set(a):
    prof, _d = need_profile()
    if not prof:
        return emit({"ok": False, "error": "desteklenmeyen model"}, 1) if _JSON() else 1
    ks = prof["keystream"]
    pmin, pmax = prof["pw_min"], prof["pw_max"]
    edits = []
    shown = {}
    pwcheck = None
    yon_arg = getattr(a, "yonetici", None)
    kul_arg = getattr(a, "kullanici", None)
    kor_arg = getattr(a, "koruma", None)
    if kor_arg:
        pwcheck = {"always": 2, "acilis": 2, "setup": 1}[kor_arg]
    if pwcheck is not None and prof.get("pwcheck_off") is None:
        msg = "bu modelde 'koruma' (parola ne zaman sorulsun) henüz desteklenmiyor"
        return emit({"ok": False, "error": msg}, 1) if _JSON() else (print(Y("  " + msg)) or 1)
    if _JSON() or yon_arg is not None or kul_arg is not None or kor_arg is not None:
        for val, key, slot in ((yon_arg, "supervisor", prof["slot_super"]),
                               (kul_arg, "user", prof["slot_user"])):
            if val is None:
                continue
            v, e = validate_pw(val, pmin, pmax)
            if e:
                if _JSON():
                    return emit({"ok": False, "error": f"{key}: {e}"}, 1)
                print(R(f"  {key}: {e}"))
                return 1
            edits.append((slot, codec.obf(v, ks)))
            shown[key] = v
        if not edits and pwcheck is None:
            if _JSON():
                return emit({"ok": False, "error": "parola/koruma verilmedi"}, 1)
            print(Y("  Parola/koruma verilmedi."))
            return 0
    else:
        print(B("\nParola ayarla ") + D("(boş bırakırsan o parola değişmez)"))
        if prof.get("pwcheck_off") is None:
            print(D("  Hangi parolayı ayarladığın, parolanın ne zaman sorulacağını belirler:"))
            print(D("    • ") + Cy("Yönetici") + D(" — yalnız BIOS ayarlarına girişi korur (sistem normal açılır)"))
            print(D("    • ") + Cy("Kullanıcı") + D(" — her açılışta sorulur (sistemi açılışta kilitler)"))
        for lbl, key, slot in (("Yönetici", "supervisor", prof["slot_super"]),
                               ("Kullanıcı", "user", prof["slot_user"])):
            raw = ui.ask_pw(f"  {lbl} parolası ({pmin}-{pmax}, boş=atla): ")
            if not raw:
                continue
            if len(raw) < pmin:
                print(R(f"    En az {pmin} karakter olmalı; atlandı."))
                continue
            v = codec.to_bios(raw, pmax)
            edits.append((slot, codec.obf(v, ks)))
            shown[key] = codec.trq(v)
        if "supervisor" in shown and prof.get("pwcheck_off") is not None:
            print(D("\n  Yönetici parolası ne zaman sorulsun? ") + D("(boş = değiştirme)"))
            print("    1) " + G("Her açılışta"))
            print("    2) " + G("Yalnız BIOS ayarlarına girerken"))
            try:
                kk = ui.ask("  Seçim [1/2]: ").strip()
            except EOFError:
                kk = ""
            pwcheck = {"1": 2, "2": 1}.get(kk)
        if not edits and pwcheck is None:
            print(Y("  Parola girilmedi."))
            return 0
        print()
        if "supervisor" in shown:
            print(f"  Yönetici : {G(shown['supervisor'])}")
        if "user" in shown:
            print(f"  Kullanıcı: {G(shown['user'])}")
        if pwcheck is not None:
            print(f"  Sorulma  : {G('her açılışta' if pwcheck == 2 else 'yalnız BIOS ayarlarına girerken')}")
        print(f"  {WARN} {Y('BIOS SPI flash değiştirilecek (CHIPSEC). Brick riski; Windows portunda donanım testi YAPILMADI.')}")
        if not ui.confirm_evet("Yazmak için EVET yazın: "):
            print(Y("  İptal edildi."))
            return 0
    out = getattr(a, "out", None)
    if out:
        res = _dryrun_write(prof, edits, pwcheck, getattr(a, "dump", None), out)
    else:
        res = _write_flow(prof, edits, pwcheck=pwcheck)
    prot = None if pwcheck is None else ("always" if pwcheck == 2 else "setup")
    if _JSON():
        return emit({"ok": res["ok"], "changed": res["changed"], "error": res["error"],
                     "verified": res.get("verified"), "out": res.get("out"),
                     "supervisor": shown.get("supervisor"), "user": shown.get("user"),
                     "protection": prot}, 0 if res["ok"] else 1)
    _write_result_print(res)
    return 0 if res["ok"] else 1


def cmd_clear(a):
    prof, _d = need_profile()
    if not prof:
        return emit({"ok": False, "error": "desteklenmeyen model"}, 1) if _JSON() else 1
    z = b"\x00" * prof["slot_len"]
    edits = {"all": [(prof["slot_user"], z), (prof["slot_super"], z)],
             "kullanici": [(prof["slot_user"], z)],
             "yonetici": [(prof["slot_super"], z)]}[a.slot]
    out = getattr(a, "out", None)
    if not _JSON() and not out:
        print(f"  {WARN} {Y('BIOS SPI flash değiştirilecek (CHIPSEC). Brick riski; Windows portunda donanım testi YAPILMADI.')}")
        if not ui.confirm_evet("Temizlemek için EVET yazın: "):
            print(Y("  İptal edildi."))
            return 0
    if out:
        res = _dryrun_write(prof, edits, None, getattr(a, "dump", None), out)
    else:
        res = _write_flow(prof, edits)
    if _JSON():
        return emit({"ok": res["ok"], "changed": res["changed"], "error": res["error"],
                     "verified": res.get("verified"), "out": res.get("out")}, 0 if res["ok"] else 1)
    _write_result_print(res)
    return 0 if res["ok"] else 1
