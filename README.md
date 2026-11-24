# markt-feed

Stündlicher Abruf öffentlicher RSS-Feeds über GitHub Actions. Quellenliste und Schlüssel liegen als Repository-Secrets vor; Archiv (`daten/archiv.enc`) und Ausgabe (`web/feed.js`) werden verschlüsselt gespeichert (AES-256-CTR + HMAC-SHA256, siehe `krypto.py`).
