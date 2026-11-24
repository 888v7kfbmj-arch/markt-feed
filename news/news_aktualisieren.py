#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Feed-Abruf (Python 3)

Holt die RSS-Feeds aus quellen.json, führt sie mit dem Archiv der letzten 30 Tage zusammen
und schreibt news-data.js (vom Dashboard gelesen) sowie news-archiv.json.
Es werden nur öffentliche Feeds gelesen; es werden keine Daten an Dritte gesendet.
"""
import json, os, re, sys, html, hashlib, datetime, time, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

HIER = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (compatible; Markt-News-Feed/1.0; Feedreader)"
TAGE = 30
MAX_JE_QUELLE = 80
RELEVANZ = re.compile(r"versicher|assekuranz|makler|vermittler|rente|altersvorsorge|riester|betriebsrente|\bbav\b|pkv|krankenversich|pflegeversich|"
                      r"kfz|gdv|solvency|\bidd\b|provision|elementar|police|insurer|insurance|rückversich|lebensversich", re.I)
# Google-News-Suche: Feed-Einträge der Form "gnews:Suchbegriff" in quellen.json
GNEWS = "https://news.google.com/rss/search?"
# Treffer aus Stellenmärkten und von konzerneigenen Websites (z. B. Kulturstiftung) nicht übernehmen
AUSSCHLUSS = re.compile(r"jobs|stellenmarkt|stellenangebot", re.I)  # Ergänzung über "ausschluss" in quellen.json


def text(el, *namen):
    for n in namen:
        x = el.find(n)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
        if x is not None and x.get("href"):
            return x.get("href")
    return ""


def bereinigen(s, n=320):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or "")).replace("\u00ad", "").replace("\u200b", "")
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:n - 1] + "…") if len(s) > n else s


MONATE = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7, "august": 8,
          "september": 9, "oktober": 10, "november": 11, "dezember": 12}


def datum(s):
    if not s:
        return None
    m = re.match(r"\s*(\d{1,2})\.\s*([A-Za-zäÄ]+)\s+(\d{4})", s)  # deutsches Datum ohne Uhrzeit, z. B. "24. November 2026"
    if m and m.group(2).lower() in MONATE:
        return datetime.datetime(int(m.group(3)), MONATE[m.group(2).lower()], int(m.group(1)), 6, 0, tzinfo=datetime.timezone.utc)
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d.astimezone(datetime.timezone.utc)


def feed_url(f):
    if f.startswith("gnews:"):
        return GNEWS + urllib.parse.urlencode({"q": f[6:].strip(), "hl": "de", "gl": "DE", "ceid": "DE:de"})
    return f


def feed_lesen(q, f):
    name = ""
    if "|" in f and not f.startswith("gnews:"):  # "Zeitung|https://…" = Anzeigename der Zeitung
        name, f = [x.strip() for x in f.split("|", 1)]
    url = feed_url(f)
    gn = url.startswith(GNEWS)
    if gn:
        time.sleep(1.5)  # Google News nicht in schneller Folge abfragen
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    raw = urllib.request.urlopen(req, timeout=30).read()
    raw = re.sub(rb"<!DOCTYPE[^>]*>", b"", raw, flags=re.I)  # keine DTD-Verarbeitung
    root = ET.fromstring(raw)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    eintraege = root.findall(".//item") or root.findall(".//a:entry", ns)
    out = []
    for it in eintraege[:MAX_JE_QUELLE]:
        if it.tag.endswith("entry"):
            t = text(it, "{http://www.w3.org/2005/Atom}title")
            u = text(it, "{http://www.w3.org/2005/Atom}link")
            d = text(it, "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published")
            s = text(it, "{http://www.w3.org/2005/Atom}summary", "{http://www.w3.org/2005/Atom}content")
        else:
            t = text(it, "title")
            u = text(it, "link", "guid")
            d = text(it, "pubDate", "{http://purl.org/dc/elements/1.1/}date")
            s = text(it, "description", "{http://purl.org/rss/1.0/modules/content/}encoded")
        herkunft = ""
        if gn:  # Google News: Titel endet auf " - Zeitung", Anriss wiederholt nur den Titel
            herkunft = bereinigen(it.findtext("source") or "", 80)
            if not herkunft or AUSSCHLUSS.search(herkunft):
                continue
            if t.endswith(" - " + herkunft):
                t = t[:-len(herkunft) - 3]
            s = ""
        t, s = bereinigen(t, 220), bereinigen(s)
        dt = datum(d)
        if not t or not u:
            continue
        if q.get("filter") and not RELEVANZ.search(t + " " + s):
            continue
        eintrag = {"id": hashlib.md5(u.encode("utf-8")).hexdigest()[:12], "q": q["id"], "t": t, "u": u.strip(),
                   "d": dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None, "s": s}
        if not dt or not re.search(r"\d{1,2}:\d{2}", d or ""):
            eintrag["nt"] = 1  # Quelle liefert keine Uhrzeit
        if herkunft or name:
            eintrag["qn"] = herkunft or name  # tatsächliche Zeitung
        if gn:
            eintrag["g"] = 1  # über Google News gefunden
        if q.get("konzern"):
            eintrag["k"] = 1  # Treffer einer als "konzern" markierten Quelle
        out.append(eintrag)
    return out


def main():
    global AUSSCHLUSS
    cfg = json.load(open(os.path.join(HIER, "quellen.json"), encoding="utf-8"))
    if cfg.get("ausschluss"):
        AUSSCHLUSS = re.compile(AUSSCHLUSS.pattern + "|" + cfg["ausschluss"], re.I)
    archiv_pfad = os.path.join(HIER, "news-archiv.json")
    alt = []
    if os.path.exists(archiv_pfad):
        try:
            alt = json.load(open(archiv_pfad, encoding="utf-8")).get("items", [])
        except Exception:
            alt = []
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    status, neu = [], []
    for q in cfg["quellen"]:
        st = {"id": q["id"], "name": q["name"], "web": q["web"], "gewicht": q.get("gewicht", 1.0), "sprache": q.get("sprache", "de")}
        if not q.get("feed"):
            st.update(ok=None, n=0, info=q.get("grund", "kein Feed"))
        else:
            try:
                items, fehler = [], []
                feeds = q["feed"] if isinstance(q["feed"], list) else [q["feed"]]
                for f in feeds:
                    try:
                        items += feed_lesen(q, f)
                    except Exception as e:
                        fehler.append(str(e)[:80])
                if fehler and len(fehler) == len(feeds):
                    raise Exception(fehler[0])
                for i in items:
                    if not i["d"]:
                        i["d"] = jetzt.strftime("%Y-%m-%dT%H:%M:%SZ")
                neu += items
                st.update(ok=True, n=len(items), info=("%d von %d Feeds nicht erreichbar" % (len(fehler), len(feeds))) if fehler else "")
                print("  ✓ %-34s %3d Artikel" % (q["name"], len(items)))
            except Exception as e:
                st.update(ok=False, n=0, info=str(e)[:160])
                print("  ✗ %-34s %s" % (q["name"], str(e)[:80]))
        status.append(st)
    # zusammenführen (neueste Fassung gewinnt), auf 30 Tage begrenzen
    grenze = (jetzt - datetime.timedelta(days=TAGE)).strftime("%Y-%m-%dT%H:%M:%SZ")
    alle = {i["u"]: i for i in alt}
    # Dubletten: Google-News-Treffer, die schon aus einem direkten Feed vorliegen (gleicher Titel), weglassen
    schluessel = lambda t: re.sub(r"[^a-z0-9äöüß]+", "", (t or "").lower())[:90]
    gesehen = {schluessel(i["t"]) for i in list(alt) + neu if not i.get("g")}
    gefiltert = []
    for i in neu:
        if i.get("g"):
            k = schluessel(i["t"])
            if k in gesehen:
                continue
            gesehen.add(k)
        gefiltert.append(i)
    neu = gefiltert
    for i in neu:
        vorher = alle.get(i["u"])
        if vorher and vorher.get("d") and vorher["d"] < i["d"]:
            i["d"] = vorher["d"]  # Erstfunddatum behalten (Feeds ohne Uhrzeit/Datum)
        alle[i["u"]] = i
    items = sorted((i for i in alle.values() if (i.get("d") or "") >= grenze), key=lambda i: i["d"], reverse=True)
    daten = {"stand": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"), "quellen": status, "items": items}
    json.dump({"items": items}, open(archiv_pfad, "w", encoding="utf-8"), ensure_ascii=False)
    with open(os.path.join(HIER, "news-data.js"), "w", encoding="utf-8") as f:
        f.write("/* automatisch erzeugt */\nwindow.FEED_DATA = ")
        json.dump(daten, f, ensure_ascii=False)
        f.write(";\n")
    ok = sum(1 for s in status if s["ok"])
    print("\nFertig: %d Artikel aus %d Quellen (Archiv %d Tage). Stand %s UTC" % (len(items), ok, TAGE, daten["stand"]))


if __name__ == "__main__":
    main()
