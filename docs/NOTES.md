# breihen.py — Entwicklungsnotizen

Stand 2026-09-11. Hintergrund zu Entscheidungen, Messungen und offenen Punkten;
Benutzung siehe [README](../README.md) und `breihen.py --help`.

Repo `~/projekte/breihen` → GitHub `Adorfer/breihen` (main, public, BSD-3).
`~/breihen.py` ist Symlink darauf. Workflow: sofort committen, pushen nur auf Zuruf
(steht in CLAUDE.md des Repos).

## Review-Runde (Opus-Review) — Befunde und Fixes

| # | Befund | Fix | Commit |
|---|---|---|---|
| 1 | RAW+JPEG gleicher Aufnahme → eine Serie doppelter Länge, NEF des Startbilds verschoben | Paarbildung: gleicher Stamm im selben Verz. = eine Aufnahme; JPEG führt, Rest Begleitdateien (gleicher Name, Aktion, Zeit) | 68f2776 |
| 2 | Schärfemessung scheitert an Bild k>1 → KeyError, bei jedem Lauf | Werte sammeln, nur bei Erfolg zuweisen; jede Ausnahme → Rückfall | 183b8a7 |
| 3 | glob-Sperre scheitert bei `[ ] * ?` im Pfad | os.listdir-Index | dd34c77 |
| 4a | Startkopie scheitert → Folgebilder trotzdem verschoben; Ctrl-C → halbe N1G-Datei | kopieren_atomar (Temp + os.replace); Start scheitert → Serie abbrechen | 6f407ef |
| 4b | halbfertige Serie gilt als "bereits abgelegt" | ablage_status je Aufnahme: neu / erledigt / UNVOLLSTAENDIG (gemeldet, Fehler, nicht angefasst) | dd34c77 |
| 5 | Zweitlauf wählt anderes schärfstes Bild → Sperre greift nicht, verschob sogar Behaltene | dieselbe ablage_status-Prüfung | dd34c77 |
| 6 | gleiche ID, fremde Serie (zwei Bodies / Zählerumlauf) | Schlüssel (SerialNumber, BurstGroupID) + automatische Zeitlücken-Trennung | d10ef21 |
| 7 | Kleinkram: exiftool-Abbruch → JSONDecodeError bricht --rekursiv ab; Encoding; mehrzeiliges Log; TIFF volle Größe; Platz-Check ohne Rang 2..k | alles behoben | 8a25dbd, 68f2776 |

Doku: 1505b45. Tests: 45fcf35 ([tests/regression.py](../tests/regression.py), 28 Prüfungen,
~25 s; gegen Stand 8f305f4 schlagen 18 fehl = genau die Befunde).

## BurstGroupID — gemessen an einer Nikon Z5II (Reisefotos, Oktober 2025)

- `BurstGroupID = (Bildnummer des 1. Serienbilds × 32) mod 65536` → alle IDs Vielfache
  von 32; Sprung zwischen Serien = 32 × Bildanzahl der vorigen (9er +288, 5er +160).
- Effektiv 11-bit-Bildzähler, **Umlauf alle 2048 Aufnahmen** (65536/32).
- Interner Zähler läuft etwas schneller als ShutterCount (Offset driftet ~+240 in
  3850 Aufnahmen) — vermutlich zählt er Frames, die ShutterCount nicht zählt.
- ~6400 Aufnahmen in 4 Tagen → 3 Umläufe; dieselbe ID an zwei aufeinanderfolgenden
  Tagen für zwei verschiedene Serien vergeben.
- Innerhalb echter Serien max. 1 s zwischen zwei Bildern → Trenngrenze
  2 × Belichtung + 30 s (SERIEN_LUECKE_AUTO) sehr sicher.
- exiftool Nikon.pm:12097: ID > 0 nur in Serienbild-Modi (CL/CH/C30/C60/C120, Pixel
  Shift), 0 im Einzelbild-Modus → Reihen müssen im Serienbild-Modus entstehen.
- Gegenprobe an echten Daten (ein Ordner, 1051 JPG): alte und neue Gruppierung identisch,
  166 Serien.

## Entscheidungen (und warum)

- **Paare: JPEG führt**, weil Pillow `draft()` die Luma direkt aus den DCT-Daten liest;
  NEF würde über die eingebettete Vorschau gemessen.
- **UNVOLLSTAENDIG wird nicht automatisch fortgesetzt**: N-Nummern hängen an der
  ursprünglichen Serienzusammensetzung; ohne Journal wäre Weitermachen geraten.
- **Ablage-Erkennung**: Startaufnahme über `<stamm>_N1G<n>_(…)<ext>`, Folgeaufnahmen
  über `…_N<i>_(…)_<originalname>` — Regexe `_ABLAGE_START` / `_ABLAGE_FOLGE`.
- **--max-gap**: None = automatisch, 0 = aus, >0 = feste Grenze.
- User-Regeln: eine Kamera je Ordner; Schärfe-Zweitlauf "so nicht einsetzen" — ist
  inzwischen trotzdem technisch abgefangen.

## Offen / bekannte Grenzen

- **dcraw_emu-Rückfall nie mit echter NEF getestet** (nur Fehlerpfad).
- **Echte NEF-Paare nie getestet** — Fake-NEFs (JPEG-Inhalt) kann exiftool nicht
  beschreiben; Zeit-Test der Begleitdateien lief mit TIFF. Erster echter RAW+JPEG-Lauf
  mit `--dry-run`, danach Zeiten der NEFs in breihen/ kontrollieren.
- **Zeit-Schreiben scheitert NACH dem Verschieben** → Dateien liegen in breihen/,
  Zeiten falsch, nur `zeit-fehler` im Log + Exit 1. Zweitlauf hält die Serie für
  erledigt und korrigiert nichts. Abhilfe wäre ein Journal oder ein
  `--zeiten-nachziehen`-Modus.
- **C120-Randfall**: eine Serie von genau 2048 Frames (oder Summe bis zur nächsten)
  → Folgeserie gleiche ID und zeitlich direkt dahinter → würde verschmolzen. Für AEB
  irrelevant.
- **--dry-run schreibt Preflight-Probedateien** (werden wieder gelöscht) — auf echten
  Shares nur rein lesend testen: read_metadata + build_groups direkt aufrufen.

## Testansatz (Kurzfassung)

`python3 tests/regression.py [-k muster] [--behalten]` — Temp-Verzeichnis,
ImageMagick-Plasma als Basisbild, exiftool für Zeit/Belichtung, `read_metadata`
umhüllt für gid/serial/ev/var. Neue Fälle: Funktion mit `@test` dekorieren.
