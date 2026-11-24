#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ver- und Entschlüsselung des Feeds.

  python krypto.py auf   daten/archiv.enc  -> news/news-archiv.json (falls vorhanden)
  python krypto.py zu    news/news-archiv.json -> daten/archiv.enc
                         news/news-data.js     -> web/feed.js (für die Web-Apps)

Schlüssel: Umgebungsvariable FEED_SCHLUESSEL (64 Byte, Base64). Verfahren: gzip, dann
AES-256-CTR (openssl) und HMAC-SHA256 über IV und Geheimtext (Encrypt-then-MAC).
Format: Base64(IV[16] | Geheimtext | Prüfsumme[32]).
"""
import base64, gzip, hashlib, hmac, json, os, subprocess, sys

HIER = os.path.dirname(os.path.abspath(__file__))


def schluessel():
    roh = base64.b64decode(os.environ.get("FEED_SCHLUESSEL", ""))
    if len(roh) != 64:
        sys.exit("FEED_SCHLUESSEL fehlt oder hat die falsche Länge")
    return roh[:32], roh[32:]


def aes_ctr(key, iv, daten):
    return subprocess.run(["openssl", "enc", "-aes-256-ctr", "-K", key.hex(), "-iv", iv.hex()],
                          input=daten, capture_output=True, check=True).stdout


def zu(daten):
    ek, mk = schluessel()
    iv = os.urandom(16)
    ct = aes_ctr(ek, iv, gzip.compress(daten, 9, mtime=0))
    return base64.b64encode(iv + ct + hmac.new(mk, iv + ct, hashlib.sha256).digest()).decode()


def auf(text):
    ek, mk = schluessel()
    roh = base64.b64decode(text)
    iv, ct, tag = roh[:16], roh[16:-32], roh[-32:]
    if not hmac.compare_digest(tag, hmac.new(mk, iv + ct, hashlib.sha256).digest()):
        sys.exit("Prüfsumme falsch – falscher Schlüssel oder beschädigte Datei")
    return gzip.decompress(aes_ctr(ek, iv, ct))


def pfad(*t):
    return os.path.join(HIER, *t)


def main():
    if sys.argv[1:] == ["auf"]:
        if os.path.exists(pfad("daten", "archiv.enc")):
            open(pfad("news", "news-archiv.json"), "wb").write(auf(open(pfad("daten", "archiv.enc")).read()))
            print("Archiv entschlüsselt")
        else:
            print("Noch kein Archiv")
    elif sys.argv[1:] == ["zu"]:
        os.makedirs(pfad("daten"), exist_ok=True)
        os.makedirs(pfad("web"), exist_ok=True)
        open(pfad("daten", "archiv.enc"), "w").write(zu(open(pfad("news", "news-archiv.json"), "rb").read()))
        raw = open(pfad("news", "news-data.js"), encoding="utf-8").read()
        d = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        for i in d["items"]:
            if i.get("u", "").startswith("http://"):
                i["u"] = "https://" + i["u"][7:]
        for q in d["quellen"]:
            q.pop("info", None)
        enc = zu(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        open(pfad("web", "feed.js"), "w").write('window.FEED_ENC="%s";\n' % enc)
        print("Verschlüsselt: %d Einträge" % len(d["items"]))
    else:
        sys.exit("Aufruf: python krypto.py auf|zu")


if __name__ == "__main__":
    main()
