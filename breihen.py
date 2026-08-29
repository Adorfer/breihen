#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
breihen.py -- Belichtungsreihen (Bracketing-Serien) einer Nikon-Kamera sortieren.

Liest per exiftool BurstGroupID und ExposureBracketValue aller Bilddateien im
Startverzeichnis, gruppiert sie zu Serien und legt sie umbenannt im
Unterverzeichnis "breihen" ab:

    1. Bild der Serie : <Start>_N1G<Groesse>_(B<EV>).<ext>          -> KOPIE
    n. Bild der Serie : <Start>_N<n>_(B<EV>)_<Originalname>.<ext>   -> VERSCHOBEN

Beispiel (Serie mit 7 Bildern, Startdatei P2140944.jpeg):
    P2140944.jpeg -> breihen/P2140944_N1G7_(B+0).jpeg
    P2140947.jpeg -> breihen/P2140944_N4_(B-2)_P2140947.jpeg

Aufnahmezeit (EXIF: DateTimeOriginal/CreateDate/ModifyDate) und Dateidatum im
Dateisystem werden je Serie vereinheitlicht:

    Startbild   -> Zeitpunkt der Startdatei              (T)
    Folgebilder -> Zeitpunkt der Startdatei + 1 Sekunde  (T + 1 s, --folge-offset)

Zwischen den Startzeitpunkten zweier aufeinanderfolgender Serien wird ein
Mindestabstand von 32 Sekunden erzwungen (--min-abstand) -- damit bleiben
zwischen den Folgebildern einer Serie (T+1) und dem Startbild der naechsten
(T+32) noch 31 Sekunden. Liegt eine Serie zu dicht hinter ihrer Vorgaengerin,
werden alle ihre Bilder nach hinten geschoben; die Verschiebung setzt sich bei
Bedarf durch die Folgeserien fort, so dass die zeitliche Reihenfolge der
Serien erhalten bleibt.

Enthaelt eine Serie ein Bild mit einer Belichtungszeit ueber 14 Sekunden
(--lange-belichtung), wird diese Belichtungszeit auf den Mindestabstand
aufgeschlagen: nach einer Serie mit 45-Sekunden-Belichtung betraegt der
Abstand zur naechsten Serie also 45 + 32 = 77 Sekunden.

Im Startverzeichnis verbleibt nur die jeweils ERSTE Datei jeder Serie --
unveraendert und unter ihrem Originalnamen.

Bearbeitet werden per Vorgabe nur echte BELICHTUNGSREIHEN, also Serien, in
denen sich der ExposureBracketValue tatsaechlich aendert. Serien, deren Bilder
alle mit derselben Belichtung aufgenommen wurden, bleiben unangetastet
liegen. Nikon kennt daneben weitere Reihenarten, die ebenfalls eine
BurstGroupID bekommen -- Blitzbelichtungsreihen, Weissabgleichreihen und
Active-D-Lighting-Reihen. Welche davon bearbeitet werden, steuert --typen
(Vorgabe "ae"); --allbracketing nimmt alle. Erkannt wird die Art daran,
welcher Wert sich innerhalb der Serie aendert:

    ae    ExposureBracketValue        (Belichtungsreihe)
    flash FlashExposureBracketValue   (Blitzbelichtungsreihe)
    wb    WhiteBalanceFineTune        (Weissabgleichreihe)
    adl   ActiveD-Lighting            (Active-D-Lighting-Reihe)
    keine nichts aendert sich         (z.B. reine Serienaufnahme)

Der Klammerblock im Dateinamen zeigt den Wert, der die Reihe ausmacht:

    (B+0.6)   Belichtungsreihe    ExposureBracketValue
    (F+1)     Blitzreihe          FlashExposureBracketValue
    (W+3)     Weissabgleichreihe  WhiteBalanceFineTune, zweiachsig z.B. (W+3-2)
    (A_High)  Active-D-Lighting   Off/Low/Normal/High/XHigh1..4/Auto
    (S1_842)  Schaerferang        nur Typ "keine", Rang und Messwert

Serien vom Typ "keine" (alle Bilder gleich aufgenommen) werden nach
Bildschaerfe geordnet: gemessen wird die Laplace-Antwort auf dem Luma-Kanal,
gewichtet auf das AF-Messfeld der Kamera. Liefert die Kamera keine
AF-Koordinaten, wird die Motivlage aus der Serie selbst geschaetzt (Stelle
mit der groessten Schaerfeaenderung zwischen den Aufnahmen, braucht scipy);
erst danach wird ersatzweise die Bildmitte gewichtet. Das
schaerfste Bild uebernimmt die Rolle der Startdatei und bleibt zusammen mit
allen Bildern, die weniger als 5 Prozent darunter liegen (--schaerfe-toleranz),
im Originalverzeichnis liegen; die uebrigen werden verschoben. --schaerfe-bericht
gibt nur die Messwerte aus und veraendert nichts. Dafuer werden numpy, Pillow
und scipy gebraucht -- siehe VORAUSSETZUNGEN am Ende.

Mit --rekursiv werden auch alle Unterverzeichnisse bearbeitet; jedes bekommt
sein eigenes Unterverzeichnis "breihen", und die Serienbildung sowie die
Zeitplanung laufen je Verzeichnis getrennt. Nicht betreten werden dabei die
selbst erzeugten "breihen"-Ordner und Verzeichnisse, deren Name mit
"PhotomatixResults" beginnt. Ohne --rekursiv wird nur das Startverzeichnis
selbst bearbeitet (Vorgabe).

Vor der ersten Schreibaktion prueft das Programm alle benoetigten Rechte
(Verzeichnis anlegen, Datei schreiben, umbenennen/verschieben, Dateidatum
setzen, loeschen) sowie den freien Speicherplatz und bricht andernfalls ab,
ohne irgendetwas zu veraendern.

Jeder Aufruf haengt sein Protokoll an eine Logdatei an (Vorgabe: breihen.log
im Startverzeichnis, aenderbar mit --logfile, abschaltbar mit --kein-log).
Eine Zeile je Vorgang im syslog/postfix-Stil, mit Zeitstempel und Prozess-ID
zum Filtern paralleler Laeufe:

    2026-08-29 12:34:56 breihen[4711]: verschoben gid=100 quelle=... ziel=...

    grep -F 'breihen[4711]' breihen.log       # ein bestimmter Lauf
    grep -E ' (zeit-)?fehler ' breihen.log     # alle Fehlschlaege

Auf einem Terminal zeigt eine einzeilige, sich selbst ueberschreibende
Statusanzeige (stderr) den Fortschritt der langen stillen Phasen an --
Metadaten lesen, Schaerfemessung, Rechtepruefung. In Pipes oder unter cron
bleibt sie automatisch stumm.


VORAUSSETZUNGEN (Paketnamen fuer Ubuntu 26.04)
==============================================

Pflicht -- ohne diese laeuft gar nichts:

    python3                   ab 3.7 (wegen subprocess capture_output und
                              from __future__ import annotations),
                              entwickelt und getestet mit 3.14
    libimage-exiftool-perl    liefert exiftool; liest und schreibt saemtliche
                              Metadaten (BurstGroupID, ExposureBracketValue,
                              Aufnahmezeit, AF-Messfeld, RAW-Vorschau)

Optional -- nur fuer die Schaerfemessung bei Serien vom Typ "keine":

    python3-pil               Pillow; dekodiert den Luma-Kanal aus dem JPEG
    python3-numpy             Rechenkern der Messung
                              (kommt automatisch mit python3-scipy)
    python3-scipy             automatische Motivsuche, wenn die Kamera keine
                              AF-Koordinaten liefert
    libraw-bin                liefert dcraw_emu; entwickelt RAW-Dateien, in
                              denen keine brauchbare Vorschau eingebettet ist

Fehlt etwas Optionales, bricht das Programm NICHT ab, sondern faellt zurueck:

    ohne numpy/Pillow  ->  keine Schaerfemessung; es bleibt wie sonst das
                           chronologisch erste Bild liegen
    ohne scipy         ->  Messfenster starr auf der Bildmitte statt auf dem
                           gefundenen Motiv (deutlich geringere Trennschaerfe)
    ohne libraw-bin    ->  RAW-Dateien nur ueber die eingebettete
                           Kamera-Vorschau; fehlt die, wird die Serie
                           uebersprungen

NICHT gebraucht werden ImageMagick, OpenCV oder ein venv.

Alles auf einmal, ausgehend von einem Ubuntu-Minimalsystem -- python3 und
python3-numpy kommen als Abhaengigkeit von python3-scipy zwangslaeufig mit,
libjpeg/libtiff/libwebp mit python3-pil, libraw mit libraw-bin:

    sudo apt install libimage-exiftool-perl python3-scipy python3-pil libraw-bin

Nur der Kern, ohne Schaerfemessung:

    sudo apt install python3 libimage-exiftool-perl

Hinweis: das System-Python ist unter Ubuntu 26.04 als EXTERNALLY-MANAGED
markiert (PEP 668). "pip install" schlaegt dort fehl -- deshalb die
apt-Pakete; alternativ ein venv (Paket python3-venv).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta

# Optional -- nur fuer die Schaerfemessung noetig.
# Installation: sudo apt install python3-numpy python3-pil
try:
    import numpy as np
    from PIL import Image
except ImportError:                                   # pragma: no cover
    np = None
    Image = None

# Optional -- ohne scipy faellt die Motivsuche auf die Bildmitte zurueck.
try:
    from scipy.ndimage import uniform_filter
except ImportError:                                   # pragma: no cover
    uniform_filter = None

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".jfif",
    ".nef", ".nrw", ".raw", ".dng", ".arw", ".cr2", ".cr3", ".raf", ".orf", ".rw2",
    ".tif", ".tiff", ".heic", ".heif", ".hif",
}

READ_TAGS = [
    "-ExposureBracketValue",
    "-BurstGroupID",
    "-DateTimeOriginal",
    "-SubSecTimeOriginal",
    "-CreateDate",
    "-ExposureTime",
    "-BulbDuration",
    # Zur Unterscheidung der Bracketing-Arten
    "-FlashExposureBracketValue",
    "-ActiveD-Lighting",
    "-WhiteBalanceFineTune",
    "-WhiteBalance",
    "-BracketSet",
    "-AutoBracketSet",
    # AF-Messfeld -- gewichtet die Schaerfemessung auf das fokussierte Motiv
    "-AFCoordinatesAvailable",
    "-AFAreaXPosition",
    "-AFAreaYPosition",
    "-AFAreaWidth",
    "-AFAreaHeight",
    "-AFImageWidth",
    "-AFImageHeight",
]

AF_TAGS = ("AFCoordinatesAvailable", "AFAreaXPosition", "AFAreaYPosition",
           "AFAreaWidth", "AFAreaHeight", "AFImageWidth", "AFImageHeight")

# Schaerfemessung
SCHAERFE_KANTE = 2000        # auf diese maximale Kantenlaenge herunterrechnen
# Aussenradius des Messfensters. Innerhalb faellt das Gewicht gaussfoermig zur
# Mitte hin ab, ausserhalb ist es hart null. Die harte Grenze ist wesentlich:
# ein unbegrenzter Gauss-Schwanz nimmt so viel scharfen Hintergrund mit, dass
# ein Bild mit Fehlfokus gewinnen kann (nachgemessen).
SCHAERFE_ROI_AF = 0.03       # Mindestradius mit AF-Daten, Anteil der Bilddiagonale
SCHAERFE_ROI_AUTO = 0.09     # Radius bei automatisch gefundenem Motiv
SCHAERFE_ROI_MITTE = 0.25    # Radius als letzter Ausweg (Bildmitte)

# Automatische Motivsuche, wenn die Kamera keine AF-Koordinaten liefert
SCHAERFE_MOTIV_KANTE = 1200      # Kantenlaenge fuer die Suche (grob genuegt)
SCHAERFE_MOTIV_FENSTER = 0.05    # Mittelungsfenster, Anteil der Bilddiagonale
SCHAERFE_MOTIV_PERZENTIL = 99.0  # Schwerpunkt der obersten 1 Prozent
RAW_EXTS = {".nef", ".nrw", ".raw", ".dng", ".arw", ".cr2", ".cr3",
            ".raf", ".orf", ".rw2"}

# Serientypen: erkannt wird, welcher Wert sich INNERHALB einer BurstGroup
# aendert -- das ist kameramodell-unabhaengig zuverlaessiger als die
# Menue-Einstellung. Die Reihenfolge bestimmt die Anzeige.
TYP_TAGS = (
    ("ae",    "ExposureBracketValue"),
    ("flash", "FlashExposureBracketValue"),
    ("wb",    "WhiteBalanceFineTune"),
    ("adl",   "ActiveD-Lighting"),
)
TYP_LABEL = {
    "ae":    "Belichtung (AE)",
    "flash": "Blitz",
    "wb":    "Weissabgleich",
    "adl":   "Active-D-Lighting",
    "keine": "keine Variation",
}
ALLE_TYPEN = ("ae", "flash", "wb", "adl", "keine")

# Kennbuchstabe im Dateinamen je Bracketing-Art
TYP_MARKER = {"ae": "B", "flash": "F", "wb": "W", "adl": "A"}

# ActiveD-Lighting: Zahlencode -> Kurztext fuer den Dateinamen
ADL_TEXT = {0: "Off", 1: "Low", 3: "Normal", 5: "High", 7: "XHigh",
            8: "XHigh1", 9: "XHigh2", 10: "XHigh3", 11: "XHigh4",
            65535: "Auto"}

# Menue-Einstellung der Kamera -- nur informativ fuer die Ausgabe.
BRACKETSET_TEXT = {0: "AE/Blitz", 1: "AE", 2: "Blitz",
                   3: "Weissabgleich", 4: "Active-D-Lighting"}
AUTOBRACKETSET_TEXT = {0: "AE & Blitz", 1: "nur AE", 2: "nur Blitz",
                       3: "Weissabgleich"}

# Verzeichnisnamen, die bei --rekursiv nicht betreten werden (Kleinschreibung,
# Praefix-Vergleich). Das jeweilige Zielverzeichnis (--dest) kommt automatisch
# dazu, damit die selbst erzeugten "breihen"-Ordner nicht erneut durchlaufen
# werden.
SKIP_DIR_PREFIXES = ("photomatixresults",)
SKIP_DIR_ANZEIGE = ("PhotomatixResults",)

# Bezugspunkt fuer die Laufzeitanzeige; main() setzt ihn beim Start neu.
START_ZEIT = time.monotonic()


# ---------------------------------------------------------------------------
# Fortschrittsanzeige und Protokoll
# ---------------------------------------------------------------------------

class Fortschritt:
    """Einzeilige, sich selbst ueberschreibende Statusanzeige.

    Nutzt nur \r und die ANSI-Sequenz zum Zeilenloeschen -- das reicht fuer
    den Zweck, laeuft ohne ncurses und stoert keine Ausgabeumleitung: ist
    stderr kein Terminal (Pipe, Cron, Logumleitung), bleibt die Anzeige
    komplett stumm. Geschrieben wird auf stderr, damit die eigentliche
    Programmausgabe auf stdout sauber bleibt; vor jeder normalen Ausgabe
    raeumt leeren() die Zeile weg.
    """

    ZEICHEN = "|/-\\"

    def __init__(self):
        self.aktiv = sys.stderr.isatty()
        self.zaehler = 0
        self.sichtbar = False
        self.zuletzt = 0.0

    def zeige(self, text):
        if not self.aktiv:
            return
        jetzt = time.monotonic()
        if jetzt - self.zuletzt < 0.1:      # Terminal nicht fluten
            return
        self.zuletzt = jetzt
        self.zaehler += 1
        breite = shutil.get_terminal_size((80, 24)).columns - 2
        zeile = "{} [{}] {}".format(self.ZEICHEN[self.zaehler % 4],
                                    laufzeit_text(), text)[:breite]
        sys.stdout.flush()
        sys.stderr.write("\r\x1b[K" + zeile)
        sys.stderr.flush()
        self.sichtbar = True

    def leeren(self):
        if self.aktiv and self.sichtbar:
            sys.stderr.write("\r\x1b[K")
            sys.stderr.flush()
            self.sichtbar = False


FORT = Fortschritt()

# Protokolldatei (siehe --logfile). Eine Zeile je Vorgang, mit Zeitstempel und
# Prozess-ID wie bei syslog/postfix, damit sich parallele Laeufe nachtraeglich
# mit grep auseinanderhalten lassen:
#     2026-08-29 12:34:56 breihen[4711]: verschoben quelle=... ziel=...
LOG_HANDLE = None


def log(text):
    if LOG_HANDLE is None:
        return
    try:
        LOG_HANDLE.write("{} breihen[{}]: {}\n".format(
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), os.getpid(), text))
        LOG_HANDLE.flush()
    except OSError:
        pass


def log_oeffnen(pfad):
    """Protokoll im Anfuegemodus oeffnen; Fehlschlag ist kein Abbruchgrund."""
    global LOG_HANDLE
    try:
        LOG_HANDLE = open(pfad, "a", encoding="utf-8")
        return True
    except OSError as exc:
        print("WARNUNG: Protokolldatei nicht schreibbar ({}): {}"
              .format(pfad, exc), file=sys.stderr)
        return False

DT_RE = re.compile(r"^\s*(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")


# ---------------------------------------------------------------------------
# exiftool-Anbindung
# ---------------------------------------------------------------------------

def _write_argfile(lines):
    """Argumentdatei fuer 'exiftool -@' schreiben (umgeht Laengenlimits der Kommandozeile)."""
    fh = tempfile.NamedTemporaryFile("w", suffix=".args", encoding="utf-8", delete=False)
    for line in lines:
        fh.write(line + "\n")
    fh.close()
    return fh.name


def exiftool_run(exiftool, opts, files):
    argfile = _write_argfile(files)
    try:
        cmd = [exiftool] + list(opts) + ["-charset", "filename=utf8", "-@", argfile]
        return subprocess.run(cmd, capture_output=True, text=True)
    finally:
        try:
            os.unlink(argfile)
        except OSError:
            pass


def laufzeit_text():
    """Laufzeit seit Programmstart als MM:SS.

    Die Minuten laufen ueber 60 hinaus weiter (z.B. 83:07) -- bei einem Lauf
    ueber eine volle Speicherkarte ist das aussagekraeftiger als Stunden.
    Gemessen mit einer monotonen Uhr, damit eine Zeitumstellung waehrend des
    Laufs die Anzeige nicht verfaelscht.
    """
    sekunden = max(0, int(time.monotonic() - START_ZEIT))
    return "{:02d}:{:02d}".format(sekunden // 60, sekunden % 60)


def parse_dt(value):
    if not value:
        return None
    m = DT_RE.match(str(value))
    if not m:
        return None
    try:
        return datetime(*(int(x) for x in m.groups()))
    except ValueError:
        return None


def read_metadata(paths, exiftool="exiftool", fortschritt=None):
    """Metadaten aller Dateien in EINEM exiftool-Aufruf lesen.

    Die JSON-Ausgabe wird streamend eingelesen: exiftool schreibt den Block
    jeder Datei, sobald sie verarbeitet ist (nachgemessen; die Pipe-Pufferung
    von Perl fasst hoechstens einige Dateien zusammen). Ueber `fortschritt`
    wird deshalb waehrend des Laufs je fertiger Datei die laufende Nummer
    gemeldet -- bei tausenden Dateien auf einem langsamen Netzlaufwerk sonst
    minutenlang Funkstille.
    """
    if not paths:
        return []
    argfile = _write_argfile(paths)
    cmd = ([exiftool, "-j", "-n", "-m", "-q", "-q"] + READ_TAGS
           + ["-charset", "filename=utf8", "-@", argfile])
    teile = []
    gesehen = 0
    try:
        with tempfile.TemporaryFile("w+", encoding="utf-8",
                                    errors="replace") as fehlerkanal:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=fehlerkanal, text=True)
            for zeile in proc.stdout:
                teile.append(zeile)
                if '"SourceFile"' in zeile:
                    gesehen += 1
                    if fortschritt is not None:
                        fortschritt(gesehen)
            proc.wait()
            fehlerkanal.seek(0)
            fehlertext = fehlerkanal.read().strip()
    finally:
        try:
            os.unlink(argfile)
        except OSError:
            pass
    out = "".join(teile).strip()
    if not out:
        if fehlertext:
            print(fehlertext, file=sys.stderr)
        return []
    data = json.loads(out)

    recs = []
    for d in data:
        path = d.get("SourceFile")
        if not path:
            continue
        name = os.path.basename(path)
        stem, ext = os.path.splitext(name)

        gid = d.get("BurstGroupID")
        try:
            gid = int(gid) if gid is not None else None
        except (TypeError, ValueError):
            gid = None

        ev = d.get("ExposureBracketValue")
        try:
            ev = float(ev) if ev is not None else None
        except (TypeError, ValueError):
            ev = None

        # Belichtungszeit in Sekunden; bei Bulb-Aufnahmen liefert Nikon die
        # tatsaechliche Dauer in BulbDuration -- der groessere Wert zaehlt.
        belichtung = 0.0
        for schluessel in ("ExposureTime", "BulbDuration"):
            try:
                wert = float(d.get(schluessel))
            except (TypeError, ValueError):
                continue
            belichtung = max(belichtung, wert)

        dt = parse_dt(d.get("DateTimeOriginal")) or parse_dt(d.get("CreateDate"))
        subsec = d.get("SubSecTimeOriginal")
        subsec = "" if subsec is None else re.sub(r"\D", "", str(subsec))

        recs.append({
            "path": path, "name": name, "stem": stem, "ext": ext,
            "gid": gid, "ev": ev, "dt": dt, "subsec": subsec,
            "belichtung": belichtung,
            # Rohwerte, an denen die Bracketing-Art erkannt wird
            "var": dict((typ, d.get(tag)) for typ, tag in TYP_TAGS),
            "bracketset": (BRACKETSET_TEXT.get(d.get("BracketSet"))
                           or AUTOBRACKETSET_TEXT.get(d.get("AutoBracketSet"))),
            "af": dict((k, d.get(k)) for k in AF_TAGS),
        })
    return recs


# ---------------------------------------------------------------------------
# Namensbildung
# ---------------------------------------------------------------------------

def format_ev(ev, mode="truncate"):
    """ExposureBracketValue als '+0', '-0.3', '+0.6', '-2' formatieren.

    Vorzeichen immer, eine Nachkommastelle, angehaengte '.0' entfaellt.
    mode='truncate': 2/3 -> 0.6 (wie in der Aufgabenstellung vorgegeben)
    mode='round'   : 2/3 -> 0.7 (kaufmaennisch gerundet)
    """
    if ev is None:
        ev = 0.0
    sign = "-" if ev < 0 else "+"
    a = abs(float(ev))
    if mode == "round":
        tenths = math.floor(a * 10 + 0.5)
    else:
        tenths = math.floor(a * 10 + 1e-9)
    s = "{:.1f}".format(tenths / 10.0)
    if s.endswith(".0"):
        s = s[:-2]
    return sign + s


def _vergleichswert(v):
    """Rohen EXIF-Wert in etwas Hashbares und robust Vergleichbares wandeln."""
    if v is None:
        return None
    if isinstance(v, (list, tuple)):
        return tuple(_vergleichswert(x) for x in v)
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return round(float(v), 3)
    return str(v).strip()


def serien_typen(group):
    """Welche Bracketing-Arten stecken in dieser Serie?

    Erkannt wird, welcher Wert sich innerhalb der Serie aendert. Eine Serie
    kann mehrere Arten gleichzeitig haben (z.B. AE und Blitz). Ein leeres
    Ergebnis bedeutet: alle Bilder wurden gleich aufgenommen -- also keine
    echte Reihe, sondern z.B. eine Serienaufnahme.
    """
    typen = set()
    for typ, _tag in TYP_TAGS:
        werte = set(_vergleichswert(r.get("var", {}).get(typ)) for r in group)
        werte.discard(None)
        if len(werte) > 1:
            typen.add(typ)
    return typen


def typ_text(typen):
    if not typen:
        return TYP_LABEL["keine"]
    return " + ".join(TYP_LABEL[t] for t, _ in TYP_TAGS if t in typen)


def typ_kurz(typen):
    """Kurzform fuer das Protokoll -- ohne Leerzeichen, z.B. 'ae+flash'."""
    if not typen:
        return "keine"
    return "+".join(t for t, _ in TYP_TAGS if t in typen)


def typ_erwuenscht(typen, erlaubt):
    """Soll eine Serie dieses Typs bearbeitet werden?"""
    if not typen:
        return "keine" in erlaubt
    return bool(typen & set(erlaubt))


def _als_float(v):
    """Rohwert in eine Zahl wandeln -- auch '1/3', '+2/3' oder '0.5'."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    m = re.match(r"^([-+]?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)$", t)
    if m:
        try:
            return float(m.group(1)) / float(m.group(2))
        except ZeroDivisionError:
            return None
    try:
        return float(t)
    except ValueError:
        return None


def _dateinamensicher(text, maxlen=12):
    """Auf Zeichen reduzieren, die unter Linux UND Windows/NTFS unbedenklich sind."""
    sauber = re.sub(r"[^A-Za-z0-9+._-]+", "", str(text))
    return sauber[:maxlen]


def format_wb(v, mode="truncate"):
    """WhiteBalanceFineTune formatieren: [3, 0] -> '+3', [3, -2] -> '+3-2'.

    Nikon liefert je nach Modell einen Wert oder zwei (Achse Bernstein/Blau und
    Achse Gruen/Magenta). Jede Komponente traegt ihr Vorzeichen, deshalb kann
    ohne Trennzeichen aneinandergehaengt werden. Reine Null-Komponenten am Ende
    entfallen.
    """
    if v is None:
        return "+0"
    teile = list(v) if isinstance(v, (list, tuple)) else [v]
    zahlen = [_als_float(x) for x in teile]
    zahlen = [z for z in zahlen if z is not None] or [0.0]
    while len(zahlen) > 1 and zahlen[-1] == 0.0:
        zahlen.pop()
    return "".join(format_ev(z, mode) for z in zahlen)


def format_adl(v):
    """ActiveD-Lighting als Kurztext: 0 -> 'Off', 5 -> 'High', 65535 -> 'Auto'."""
    if v is None:
        return "n.a."
    zahl = _als_float(v)
    if zahl is not None and float(zahl).is_integer():
        code = int(zahl)
        return ADL_TEXT.get(code, str(code))
    return _dateinamensicher(v) or "n.a."


def marker(rec, typen, ev_mode="truncate"):
    """Der Klammerblock im Dateinamen -- richtet sich nach der Bracketing-Art.

        Belichtungsreihe (AE)   (B+0.6)   ExposureBracketValue
        Blitzreihe              (F+1)     FlashExposureBracketValue
        Weissabgleichreihe      (W+3)     WhiteBalanceFineTune
        Active-D-Lighting       (A_High)  ActiveD-Lighting
        Serie nach Schaerfe     (S1_842)  Rang und Messwert

    Bei Mischformen (z.B. AE und Blitz gleichzeitig) gewinnt die in TYP_TAGS
    zuerst genannte Art. Serien ohne erkennbare Variation behalten (B...),
    also die Belichtungskorrektur.
    """
    # Serie ohne Bracketing-Variation, aber nach Schaerfe geordnet
    if not typen and rec.get("schaerfe") is not None:
        return "S{}_{}".format(rec.get("rang", 1), int(round(rec["schaerfe"])))

    werte = rec.get("var") or {}
    for typ, _tag in TYP_TAGS:
        if typ not in typen:
            continue
        if typ == "ae":
            break                                  # unten als Vorgabe behandelt
        if typ == "flash":
            zahl = _als_float(werte.get("flash"))
            if zahl is None:
                return "F" + (_dateinamensicher(werte.get("flash")) or "0")
            return "F" + format_ev(zahl, ev_mode)
        if typ == "wb":
            return "W" + format_wb(werte.get("wb"), ev_mode)
        if typ == "adl":
            return "A_" + format_adl(werte.get("adl"))
    return "B" + format_ev(rec.get("ev"), ev_mode)


def sort_key(rec):
    dt = rec["dt"] or datetime.min
    sub = float("0." + rec["subsec"]) if rec["subsec"] else 0.0
    return (dt, sub, rec["name"])


def build_groups(recs, min_size=2, max_gap=0.0):
    """Nach BurstGroupID gruppieren, innerhalb der Gruppe nach Aufnahmezeit sortieren."""
    by_gid = {}
    skipped = []
    for r in recs:
        if not r["gid"]:          # None oder 0 == kein Serienbild
            skipped.append(r)
            continue
        by_gid.setdefault(r["gid"], []).append(r)

    groups = []
    for gid in sorted(by_gid):
        items = sorted(by_gid[gid], key=sort_key)

        # Optional: gleiche BurstGroupID, aber grosser zeitlicher Abstand
        # (z.B. Zaehler-Ueberlauf der Kamera) -> in Teilserien zerlegen.
        chunks = [items]
        if max_gap > 0:
            chunks, cur = [], [items[0]]
            for prev, cur_rec in zip(items, items[1:]):
                if prev["dt"] and cur_rec["dt"] and \
                        (cur_rec["dt"] - prev["dt"]).total_seconds() > max_gap:
                    chunks.append(cur)
                    cur = []
                cur.append(cur_rec)
            chunks.append(cur)

        for c in chunks:
            if len(c) >= min_size:
                groups.append(c)
            else:
                skipped.extend(c)
    groups.sort(key=lambda g: sort_key(g[0]))
    return groups, skipped


def langzeit_zuschlag(group, schwelle=14.0):
    """Zuschlag zum Mindestabstand wegen Langzeitbelichtung.

    Enthaelt die Serie mindestens ein Bild mit einer Belichtungszeit ueber
    schwelle Sekunden, wird der laengste dieser Werte zurueckgegeben (z.B.
    45 s), sonst 0. Begruendung: waehrend einer 45-Sekunden-Belichtung
    vergeht echte Zeit, die naechste Serie kann also fruehestens
    45 s + Mindestabstand spaeter beginnen.
    """
    lang = [r.get("belichtung") or 0.0 for r in group]
    lang = [b for b in lang if b > schwelle]
    return max(lang) if lang else 0.0


def enforce_min_spacing(groups, min_spacing=32.0, langzeit_schwelle=14.0):
    """Jeder Serie eine Aufnahmezeit zuweisen und einen Mindestabstand erzwingen.

    Die Serien sind bereits chronologisch sortiert. Liegt eine Serie weniger
    als (min_spacing + Langzeit-Zuschlag der Vorgaengerin) Sekunden nach ihrer
    Vorgaengerin, wird sie entsprechend nach hinten geschoben. Da die
    verschobene Zeit ihrerseits zur Vorgaengerzeit der naechsten Serie wird,
    pflanzt sich die Verschiebung automatisch so weit fort wie noetig -- die
    zeitliche Reihenfolge der Serien bleibt dabei zwingend erhalten, denn die
    zugewiesenen Zeiten wachsen streng monoton.

    Der Zuschlag stammt immer von der VORHERIGEN Serie: deren lange Belichtung
    verbraucht die Zeit, die bis zur naechsten Serie zusaetzlich vergehen muss.

    Serien ohne DateTimeOriginal bleiben unberuecksichtigt und unterbrechen
    die Kette nicht.

    Rueckgabe: Liste [(zugewiesene_zeit, verschiebung_in_sek, zuschlag_in_sek),
    ...], parallel zu groups.
    """
    schedule = []
    prev = None
    prev_zuschlag = 0.0
    for g in groups:
        orig = g[0]["dt"]
        if orig is None:
            schedule.append((None, 0.0, 0.0))
            continue
        neu = orig
        if prev is not None and min_spacing > 0:
            frueheste = prev + timedelta(seconds=min_spacing + prev_zuschlag)
            if neu < frueheste:
                neu = frueheste
        zuschlag = langzeit_zuschlag(g, langzeit_schwelle) if min_spacing > 0 else 0.0
        schedule.append((neu, (neu - orig).total_seconds(), zuschlag))
        prev = neu
        prev_zuschlag = zuschlag
    return schedule


def plan_group(group, destdir, ev_mode="truncate", typen=None, bleiben=1):
    """Liefert (Startdatei, [(record, zielpfad, aktion), ...]).

    Die ersten `bleiben` Bilder werden kopiert und bleiben damit im
    Originalverzeichnis liegen; alle uebrigen werden verschoben. Normalerweise
    ist das nur die Startdatei; bei nach Schaerfe geordneten Serien koennen es
    mehrere sein (alle innerhalb der Schaerfetoleranz).
    """
    typen = typen or set()
    bleiben = max(1, int(bleiben))
    start = group[0]
    size = len(group)
    ops = []
    for i, r in enumerate(group, 1):
        mk = marker(r, typen, ev_mode)
        if i == 1:
            newname = "{}_N1G{}_({}){}".format(start["stem"], size, mk, r["ext"])
        else:
            newname = "{}_N{}_({})_{}{}".format(start["stem"], i, mk, r["stem"], r["ext"])
        action = "copy" if i <= bleiben else "move"
        ops.append((r, os.path.join(destdir, newname), action))
    return start, ops


# ---------------------------------------------------------------------------
# Zeitstempel setzen
# ---------------------------------------------------------------------------

def set_times(targets, dt, subsec, exiftool="exiftool"):
    """EXIF-Aufnahmezeit und Dateidatum aller Zieldateien auf dt setzen."""
    if not targets or dt is None:
        return True, ""
    stamp = dt.strftime("%Y:%m:%d %H:%M:%S")
    opts = [
        "-m", "-q", "-q", "-overwrite_original",
        "-AllDates=" + stamp,
        "-SubSecTimeOriginal=" + subsec,
        "-SubSecTimeDigitized=" + subsec,
        "-SubSecTime=" + subsec,
        "-FileModifyDate=" + stamp,
    ]
    proc = exiftool_run(exiftool, opts, targets)
    return proc.returncode == 0, (proc.stderr or "").strip()


# ---------------------------------------------------------------------------
# Schaerfemessung (nur fuer Serien vom Typ "keine")
# ---------------------------------------------------------------------------

def schaerfe_verfuegbar():
    return np is not None and Image is not None


def _vorschau_datei(pfad, exiftool, tmpdir):
    """Bildquelle zum Messen liefern.

    JPEG & Co. werden direkt gelesen. Aus RAW-Dateien holt exiftool die
    eingebettete Kamera-Vorschau -- die ist fuer alle Bilder einer Serie
    identisch entwickelt und damit sauberer vergleichbar als eine eigene
    RAW-Entwicklung; ein RAW-Dekoder wird so gar nicht erst gebraucht.
    """
    if os.path.splitext(pfad)[1].lower() not in RAW_EXTS:
        return pfad
    ziel = os.path.join(tmpdir, os.path.basename(pfad) + ".vorschau.jpg")
    for tag in ("-JpgFromRaw", "-PreviewImage", "-OtherImage", "-ThumbnailImage"):
        with open(ziel, "wb") as fh:
            subprocess.run([exiftool, "-b", tag, pfad], stdout=fh,
                           stderr=subprocess.DEVNULL)
        if os.path.getsize(ziel) > 4096:
            return ziel

    # Keine brauchbare Vorschau eingebettet -> RAW tatsaechlich entwickeln.
    # Halbe Aufloesung (-h) genuegt fuer den Vergleich und umgeht das
    # Demosaicing, das feine Details ohnehin glaettet. Die RAW-Datei wird
    # vorher kopiert, damit dcraw_emu nichts in das Verzeichnis des Nutzers
    # schreibt.
    if shutil.which("dcraw_emu") is None:
        return None
    kopie = os.path.join(tmpdir, "raw_" + os.path.basename(pfad))
    ausgabe = kopie + ".tiff"
    try:
        shutil.copy2(pfad, kopie)
        subprocess.run(["dcraw_emu", "-h", "-T", "-w", "-Z", ausgabe, kopie],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    if os.path.exists(ausgabe) and os.path.getsize(ausgabe) > 4096:
        return ausgabe
    return None


def _luma(pfad, kante=None):
    """Luma-Kanal (Y) als float32-Array.

    Bei JPEG dekodiert Pillows draft() direkt aus den DCT-Koeffizienten nach
    Graustufen und rechnet dabei gleich herunter. Das ist nicht nur schnell,
    sondern auch genauer als der Umweg ueber RGB: die Chrominanz liegt im
    JPEG meist nur in halber Aufloesung vor und wuerde die feinen Details
    verwaessern, um die es hier geht. Bewusst NICHT linearisiert -- der
    gammakodierte Y-Kanal entspricht dem wahrgenommenen Kontrast und
    verstaerkt kein Schattenrauschen.
    """
    kante = kante or SCHAERFE_KANTE
    with Image.open(pfad) as im:
        im.draft("L", (kante, kante))
        grau = im.convert("L")
        return np.asarray(grau, dtype=np.float32)


def _glaetten3(a):
    """3x3-Mittelwert: daempft Einzelpixel-Rauschen, laesst echte Kanten stehen."""
    out = a.copy()
    out[1:-1, 1:-1] = (a[:-2, :-2] + a[:-2, 1:-1] + a[:-2, 2:] +
                       a[1:-1, :-2] + a[1:-1, 1:-1] + a[1:-1, 2:] +
                       a[2:, :-2] + a[2:, 1:-1] + a[2:, 2:]) / 9.0
    return out


def _laplace(a):
    """4er-Nachbarschaft-Laplace -- misst hochfrequente Bilddetails."""
    l = np.zeros_like(a)
    l[1:-1, 1:-1] = (a[:-2, 1:-1] + a[2:, 1:-1] + a[1:-1, :-2] + a[1:-1, 2:]
                     - 4.0 * a[1:-1, 1:-1])
    return l


def _lokale_schaerfe(arr, fenster):
    """Karte der lokalen Detailenergie."""
    lap = _laplace(_glaetten3(arr))
    return uniform_filter(lap * lap, size=fenster)


def _af_position(group, breite, hoehe):
    """AF-Feldmitte und -breite in Pixeln der angegebenen Groesse, sonst None."""
    for r in group:
        af = r.get("af") or {}
        if not af.get("AFCoordinatesAvailable"):
            continue
        try:
            rw = float(af["AFImageWidth"])
            rh = float(af["AFImageHeight"])
            bx = float(af["AFAreaXPosition"])
            by = float(af["AFAreaYPosition"])
        except (TypeError, ValueError, KeyError):
            continue
        if rw <= 0 or rh <= 0:
            continue
        try:
            afbreite = float(af.get("AFAreaWidth") or 0) / rw * breite
        except (TypeError, ValueError):
            afbreite = 0.0
        return bx / rw * breite, by / rh * hoehe, afbreite
    return None


def motiv_finden(quellen):
    """Motivlage schaetzen, wenn die Kamera keine AF-Koordinaten liefert.

    Gesucht wird die Stelle, an der sich die Schaerfe zwischen den Aufnahmen
    am staerksten aendert -- genau dort steckt die Information, die ueber
    scharf und unscharf entscheidet. Eine feste Gewichtung auf die Bildmitte
    verfehlt ein Motiv am Bildrand: nachgemessen schrumpfte der Vorsprung des
    besten Bildes dadurch von 77 auf 4 Prozent, lag also unter der Toleranz.

    Laeuft auf stark verkleinerten Bildern und haelt nur ein laufendes Maximum
    und Minimum -- der Speicherbedarf haengt damit nicht von der Serienlaenge
    ab. Rueckgabe: (x, y) relativ im Bereich 0..1, oder None.
    """
    if uniform_filter is None or len(quellen) < 2:
        return None
    hoch = tief = None
    for nr, q in enumerate(quellen, 1):
        FORT.zeige("Schaerfe: Motivsuche {} ({}/{})".format(
            os.path.basename(q), nr, len(quellen)))
        try:
            arr = _luma(q, SCHAERFE_MOTIV_KANTE)
        except OSError:
            return None
        if arr.ndim != 2 or min(arr.shape) < 32:
            return None
        fenster = max(8, int(round(SCHAERFE_MOTIV_FENSTER
                                   * math.hypot(arr.shape[1], arr.shape[0]))))
        karte = _lokale_schaerfe(arr, fenster)
        if hoch is None:
            hoch, tief = karte.copy(), karte.copy()
        elif hoch.shape != karte.shape:
            return None                     # unterschiedliche Bildgroessen
        else:
            np.maximum(hoch, karte, out=hoch)
            np.minimum(tief, karte, out=tief)

    spanne = hoch - tief
    if not np.isfinite(spanne).all() or float(spanne.max()) <= 0:
        return None
    maske = (spanne >= float(np.percentile(spanne, SCHAERFE_MOTIV_PERZENTIL)))
    maske = maske.astype(np.float32)
    summe = float(maske.sum())
    if summe <= 0:
        return None
    hoehe, breite = spanne.shape
    y = np.arange(hoehe, dtype=np.float32)[:, None]
    x = np.arange(breite, dtype=np.float32)[None, :]
    return (float((maske * x).sum() / summe) / breite,
            float((maske * y).sum() / summe) / hoehe)


def af_fenster(group, form, auto=None):
    """Gauss-Gewichtung um das AF-Messfeld, ersatzweise um die Bildmitte.

    Bewusst EIN Fenster fuer die ganze Serie: wandert das AF-Feld zwischen den
    Aufnahmen (Motivverfolgung), wuerden sonst verschiedene Bildbereiche
    miteinander verglichen und die Messwerte waeren wertlos. Weiches Fenster
    statt hartem Ausschnitt, weil das AF-Feld nur wenige Prozent der Flaeche
    ausmacht und eine Messung allein darin verrauscht waere.
    """
    hoehe, breite = form
    diagonale = math.hypot(breite, hoehe)

    pos = _af_position(group, breite, hoehe)
    if pos is not None:
        mx, my, afbreite = pos
        aussen = max(afbreite / 2.0, SCHAERFE_ROI_AF * diagonale)   # Scheibe = AF-Feld
        quelle = "AF-Feld"
    elif auto is not None:
        mx, my = auto[0] * breite, auto[1] * hoehe
        aussen = SCHAERFE_ROI_AUTO * diagonale
        quelle = "Motivsuche"
    else:
        mx, my = breite / 2.0, hoehe / 2.0
        aussen = SCHAERFE_ROI_MITTE * diagonale
        quelle = "Bildmitte"

    # Mittelpunkt sicherheitshalber ins Bild zwingen (fehlerhafte Angaben)
    mx = min(max(mx, 0.0), breite - 1.0)
    my = min(max(my, 0.0), hoehe - 1.0)
    sigma = max(aussen / 2.0, 1.0)

    y = np.arange(hoehe, dtype=np.float32)[:, None]
    x = np.arange(breite, dtype=np.float32)[None, :]
    d2 = (x - mx) ** 2 + (y - my) ** 2
    gewicht = np.exp(-(d2 / (2.0 * sigma * sigma)))
    gewicht[d2 > aussen * aussen] = 0.0
    return gewicht.astype(np.float32), quelle


def messe_schaerfe(group, exiftool="exiftool"):
    """Jedem Bild der Serie einen Schaerfewert geben.

    Messwert = gewichteter Effektivwert der Laplace-Antwort auf dem Luma-Kanal,
    normiert auf die mittlere Helligkeit (macht Werte ueber Serien hinweg
    vergleichbar). Hoeher = schaerfer.

    Rueckgabe: (True, herkunft_des_fensters) oder (False, grund).
    """
    if not schaerfe_verfuegbar():
        return False, ("numpy/Pillow fehlen -- sudo apt install "
                       "libimage-exiftool-perl python3-scipy python3-pil libraw-bin")
    tmpdir = tempfile.mkdtemp(prefix="breihen_schaerfe_")
    gewicht = None
    quelle = "Bildmitte"
    try:
        quellen = []
        for nr, r in enumerate(group, 1):
            FORT.zeige("Schaerfe: Vorschau {} ({}/{}) Serie {}".format(
                r["name"], nr, len(group), r["gid"]))
            quelldatei = _vorschau_datei(r["path"], exiftool, tmpdir)
            if quelldatei is None:
                return False, "keine lesbaren Bilddaten in " + r["name"]
            quellen.append(quelldatei)

        # Messfenster EINMAL fuer die ganze Serie festlegen. Ohne AF-Daten der
        # Kamera wird die Motivlage aus der Serie selbst geschaetzt.
        auto = None
        if _af_position(group, 1.0, 1.0) is None:
            auto = motiv_finden(quellen)

        for nr, (r, quelldatei) in enumerate(zip(group, quellen), 1):
            FORT.zeige("Schaerfe: messe {} ({}/{}) Serie {}".format(
                r["name"], nr, len(group), r["gid"]))
            arr = _luma(quelldatei)
            if arr.ndim != 2 or min(arr.shape) < 8:
                return False, "Bild zu klein: " + r["name"]
            if gewicht is None or gewicht.shape != arr.shape:
                gewicht, quelle = af_fenster(group, arr.shape, auto)
            lap = _laplace(_glaetten3(arr))
            summe = float(gewicht.sum())
            if summe <= 0:
                return False, "leeres Messfenster"
            rms = math.sqrt(float((gewicht * lap * lap).sum()) / summe)
            mittel = float((gewicht * arr).sum() / summe)
            r["schaerfe"] = rms / (mittel + 1.0) * 10000.0
    except (OSError, ValueError) as exc:
        return False, str(exc)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return True, quelle


def nach_schaerfe_ordnen(group, toleranz=0.05):
    """Serie absteigend nach Schaerfe sortieren und Raenge vergeben.

    Rueckgabe: Anzahl der Bilder, die im Originalverzeichnis liegen bleiben --
    das schaerfste plus alle, die weniger als toleranz darunter liegen.
    """
    group.sort(key=lambda r: (-(r.get("schaerfe") or 0.0), r["name"]))
    for rang, r in enumerate(group, 1):
        r["rang"] = rang
    best = group[0].get("schaerfe") or 0.0
    if best <= 0:
        return 1
    grenze = best * (1.0 - toleranz)
    return sum(1 for r in group if (r.get("schaerfe") or 0.0) >= grenze)


def bereits_erledigt(destdir, stem):
    """Wurde diese Serie schon einmal abgelegt? Erkennbar am _N1G-Ergebnis.

    Noetig, seit bei Schaerfe-Serien mehrere Bilder liegen bleiben duerfen:
    ohne diese Sperre wuerde ein zweiter Lauf sie erneut als Serie auffassen.
    """
    return bool(glob.glob(os.path.join(destdir, glob.escape(stem) + "_N1G*")))


# ---------------------------------------------------------------------------
# Rechtepruefung (Preflight)
# ---------------------------------------------------------------------------

def _test_verzeichnis(d, zweck):
    """Praktischer Schreibtest in d: anlegen, schreiben, umbenennen,
    Dateidatum setzen, loeschen. Prueft echtes Verhalten statt nur die
    Permission-Bits -- wichtig auf WSL-Mounts (drvfs/NTFS), Netzlaufwerken
    und read-only gemounteten Dateisystemen, wo os.access() luegen kann.
    Rueckgabe: Liste von Fehlertexten (leer = alles in Ordnung).
    """
    fehler = []
    probe = os.path.join(d, ".breihen_schreibtest_{}".format(os.getpid()))
    ziel = probe + ".umbenannt"
    try:
        with open(probe, "wb") as fh:
            fh.write(b"breihen-schreibtest")
            fh.flush()
            os.fsync(fh.fileno())
    except OSError as exc:
        return ["{}: Datei anlegen/schreiben nicht moeglich ({})".format(zweck, exc)]

    aktuell = probe
    try:
        os.rename(probe, ziel)
        aktuell = ziel
    except OSError as exc:
        fehler.append("{}: Umbenennen/Verschieben nicht moeglich ({})".format(zweck, exc))
    try:
        os.utime(aktuell, (1700000000, 1700000000))
    except OSError as exc:
        fehler.append("{}: Dateidatum setzen nicht moeglich ({})".format(zweck, exc))
    try:
        os.unlink(aktuell)
    except OSError as exc:
        fehler.append("{}: Aufraeumen/Loeschen nicht moeglich ({}) -- "
                      "Testdatei {} bitte von Hand entfernen"
                      .format(zweck, exc, aktuell))
    return fehler


def _mb(n):
    return "{:.1f} MB".format(n / 1e6)


def preflight_rechte(startdir, destdir, groups):
    """Alle im Verzeichnis startdir benoetigten Rechte pruefen."""
    fehler = []

    # 1) Verzeichnis lesbar und betretbar
    if not os.access(startdir, os.R_OK | os.X_OK):
        return ["Verzeichnis nicht lesbar/betretbar: " + startdir]

    # 2) Verzeichnis beschreibbar -- dort wird das Unterverzeichnis angelegt
    #    und aus dort heraus werden Dateien verschoben.
    fehler += _test_verzeichnis(startdir, "Verzeichnis " + startdir)

    # 3) Zielverzeichnis
    if os.path.exists(destdir):
        if not os.path.isdir(destdir):
            fehler.append("Zielpfad existiert, ist aber kein Verzeichnis: " + destdir)
        else:
            fehler += _test_verzeichnis(destdir, "Zielverzeichnis " + destdir)
    elif not fehler:
        # mkdir-Faehigkeit pruefen, ohne das Zielverzeichnis vorab anzulegen
        probe = os.path.join(startdir, ".breihen_mkdir_test_{}".format(os.getpid()))
        try:
            os.mkdir(probe)
        except OSError as exc:
            fehler.append("Unterverzeichnis kann in {} nicht angelegt werden ({})"
                          .format(startdir, exc))
        else:
            fehler += _test_verzeichnis(probe, "neues Zielverzeichnis in " + startdir)
            try:
                os.rmdir(probe)
            except OSError as exc:
                fehler.append("Testverzeichnis {} nicht loeschbar ({})".format(probe, exc))

    # 4) Quelldateien
    euid = os.geteuid()
    ist_root = (euid == 0)
    try:
        sticky = bool(os.stat(startdir).st_mode & stat.S_ISVTX)
    except OSError:
        sticky = False
    nicht_lesbar, nicht_schreibbar, fremd = [], [], []

    geprueft = 0
    for g in groups:
        for i, r in enumerate(g):
            pfad = r["path"]
            geprueft += 1
            if geprueft % 20 == 0:
                FORT.zeige("pruefe Dateien: {} in {}".format(geprueft, startdir))
            try:
                with open(pfad, "rb") as fh:
                    fh.read(1)
            except OSError as exc:
                nicht_lesbar.append("{} ({})".format(r["name"], exc.strerror or exc))
                continue
            if i == 0:
                continue          # Startdatei wird nur gelesen und kopiert
            if not os.access(pfad, os.W_OK):
                nicht_schreibbar.append(r["name"])
            elif not ist_root:
                try:
                    if os.stat(pfad).st_uid != euid:
                        fremd.append(r["name"])
                except OSError:
                    pass

    def sammeln(liste, text):
        if not liste:
            return
        bsp = ", ".join(liste[:5]) + (" ..." if len(liste) > 5 else "")
        fehler.append("{} in {} ({} Datei(en)): {}"
                      .format(text, startdir, len(liste), bsp))

    sammeln(nicht_lesbar, "Nicht lesbar")
    sammeln(nicht_schreibbar, "Nicht beschreibbar (werden verschoben und "
                              "von exiftool ueberschrieben)")
    if fremd:
        sammeln(fremd, "Gehoeren einem anderen Benutzer -- {}Dateidatum "
                       "laesst sich nicht setzen"
                       .format("Verschieben (Sticky-Bit) und " if sticky else ""))
    return fehler


def preflight_platz(plaene, reserve_prozent=2.0):
    """Freien Speicherplatz pruefen -- je Dateisystem und ueber alle
    Verzeichnisse hinweg aufsummiert.

    Neu geschrieben werden nur die Kopien der Startdateien; alle uebrigen
    Bilder werden verschoben und belegen keinen zusaetzlichen Platz. Waehrend
    exiftool eine Datei umschreibt, existiert sie kurzzeitig doppelt -- dafuer
    die groesste Einzeldatei als Spitzenbedarf. Zusaetzlich muessen
    reserve_prozent der Gesamtkapazitaet des Dateisystems frei bleiben.
    """
    fehler = []
    pro_geraet = {}                      # st_dev -> [beispielpfad, kopien, spitze]
    for pl in plaene:
        try:
            dev = os.stat(pl["dir"]).st_dev
        except OSError as exc:
            fehler.append("Speicherplatz nicht pruefbar fuer {}: {}".format(pl["dir"], exc))
            continue
        eintrag = pro_geraet.setdefault(dev, [pl["dir"], 0, 0])
        for g in pl["groups"]:
            try:
                eintrag[1] += os.path.getsize(g[0]["path"])
                eintrag[2] = max(eintrag[2], max(os.path.getsize(r["path"]) for r in g))
            except OSError:
                pass

    for pfad, kopien, spitze in pro_geraet.values():
        try:
            nutzung = shutil.disk_usage(pfad)
        except OSError as exc:
            fehler.append("Speicherplatz nicht pruefbar: {}".format(exc))
            continue
        reserve = nutzung.total * reserve_prozent / 100.0
        noetig = kopien + spitze + reserve
        if noetig > nutzung.free:
            fehler.append(
                "Zu wenig freier Speicher auf dem Datentraeger von {}: "
                "benoetigt {} (Kopien der Startdateien {} + exiftool-Spitze {} "
                "+ {:g}% Reserve {}), verfuegbar nur {} von {}."
                .format(pfad, _mb(noetig), _mb(kopien), _mb(spitze),
                        reserve_prozent, _mb(reserve), _mb(nutzung.free),
                        _mb(nutzung.total)))
    return fehler


def preflight(plaene, reserve_prozent=2.0):
    """Rechte UND Speicherplatz fuer ALLE zu bearbeitenden Verzeichnisse
    pruefen, BEVOR irgendwo kopiert, verschoben oder geschrieben wird.
    Rueckgabe: Liste von Fehlertexten (leer = alles in Ordnung).
    """
    fehler = []
    for nr, pl in enumerate(plaene, 1):
        FORT.zeige("pruefe Rechte ({}/{}): {}".format(nr, len(plaene), pl["dir"]))
        fehler += preflight_rechte(pl["dir"], pl["dest"], pl["groups"])
    if not fehler:
        FORT.zeige("pruefe Speicherplatz")
        fehler += preflight_platz(plaene, reserve_prozent)
    FORT.leeren()
    return fehler


# ---------------------------------------------------------------------------
# Verzeichnisse einsammeln
# ---------------------------------------------------------------------------

def verzeichnis_ueberspringen(name, destname):
    """Selbst erzeugte Zielverzeichnisse und Photomatix-Ausgaben auslassen."""
    klein = name.lower()
    if klein == destname.lower():
        return True
    return any(klein.startswith(pre) for pre in SKIP_DIR_PREFIXES)


def collect_dirs(startdir, destname, rekursiv=False):
    """Zu bearbeitende Verzeichnisse ermitteln.
    Rueckgabe: (verzeichnisse, uebersprungene_verzeichnisse)
    """
    if not rekursiv:
        return [startdir], []
    verzeichnisse, uebersprungen = [], []
    for wurzel, unterverz, _dateien in os.walk(startdir, followlinks=False):
        behalten = []
        for d in sorted(unterverz):
            if verzeichnis_ueberspringen(d, destname):
                uebersprungen.append(os.path.join(wurzel, d))
            else:
                behalten.append(d)
        unterverz[:] = behalten          # steuert den weiteren Abstieg
        verzeichnisse.append(wurzel)
    return verzeichnisse, uebersprungen


def collect_files(verzeichnis):
    files = []
    try:
        eintraege = list(os.scandir(verzeichnis))
    except OSError:
        return files
    for entry in eintraege:
        if not entry.is_file(follow_symlinks=False):
            continue
        if os.path.splitext(entry.name)[1].lower() in IMAGE_EXTS:
            files.append(entry.path)
    files.sort()
    return files


# ---------------------------------------------------------------------------
# Analyse und Ausfuehrung je Verzeichnis
# ---------------------------------------------------------------------------

def analysiere(verzeichnis, args):
    """Nur lesend: Metadaten holen, Serien bilden, Zeiten planen.
    Rueckgabe: Plan-Dictionary oder None, wenn keine Bilddateien vorhanden.
    """
    files = collect_files(verzeichnis)
    if not files:
        return None
    FORT.zeige("lese Metadaten: 0/{} in {}".format(len(files), verzeichnis))
    recs = read_metadata(files, args.exiftool,
                         fortschritt=lambda n: FORT.zeige(
                             "lese Metadaten: {}/{} in {}".format(
                                 n, len(files), verzeichnis)))
    groups, skipped = build_groups(recs, args.min_size, args.max_gap)

    # Nach Bracketing-Art filtern, BEVOR die Zeiten geplant werden -- ignorierte
    # Serien bleiben unangetastet und duerfen den Mindestabstand nicht
    # beeinflussen.
    behalten, behalten_typen, ignoriert = [], [], []
    for g in groups:
        typen = serien_typen(g)
        if typ_erwuenscht(typen, args.typen):
            behalten.append(g)
            behalten_typen.append(typen)
        else:
            ignoriert.append((g, typen))
            log("uebergangen gid={} dir={} typ={} bilder={}".format(
                g[0]["gid"], verzeichnis, typ_kurz(typen), len(g)))

    # Serien ohne Bracketing-Variation nach Schaerfe ordnen. Das schaerfste
    # Bild uebernimmt danach die Rolle der Startdatei -- Basisname, Zeitstempel
    # und _N1G<n>. Muss vor der Zeitplanung geschehen, weil diese sich am
    # jeweils ersten Bild der Serie orientiert.
    bleiben_liste = [1] * len(behalten)
    schaerfe_hinweise = []
    for nr, (g, typen) in enumerate(zip(behalten, behalten_typen)):
        if typen or not args.schaerfe:
            continue
        ok, info = messe_schaerfe(g, args.exiftool)
        if ok:
            bleiben_liste[nr] = nach_schaerfe_ordnen(g, args.schaerfe_toleranz / 100.0)
            schaerfe_hinweise.append((g, info, bleiben_liste[nr]))
            log("schaerfe gid={} dir={} fenster={} bleiben={} werte={}".format(
                g[0]["gid"], verzeichnis, info, bleiben_liste[nr],
                ",".join("{}:{}".format(r["name"], int(round(r["schaerfe"])))
                         for r in g)))
        else:
            schaerfe_hinweise.append((g, "FEHLER: " + info, 1))
            log("schaerfe-fehler gid={} dir={} grund={}".format(
                g[0]["gid"], verzeichnis, info))

    # Nach dem Umsortieren kann sich das erste Bild einer Serie geaendert
    # haben -- Serien wieder chronologisch anordnen.
    ordnung = sorted(range(len(behalten)), key=lambda i: sort_key(behalten[i][0]))
    behalten = [behalten[i] for i in ordnung]
    behalten_typen = [behalten_typen[i] for i in ordnung]
    bleiben_liste = [bleiben_liste[i] for i in ordnung]

    return {
        "dir": verzeichnis,
        "relpfad": os.path.relpath(verzeichnis, getattr(args, "startdir", verzeichnis)),
        "dest": os.path.join(verzeichnis, args.dest),
        "files": files,
        "groups": behalten,
        "typen": behalten_typen,
        "bleiben": bleiben_liste,
        "schaerfe": schaerfe_hinweise,
        "ignoriert": ignoriert,
        "skipped": skipped,
        "schedule": enforce_min_spacing(behalten, args.min_abstand,
                                        args.lange_belichtung),
    }


def verarbeite(plan, args):
    """Einen Verzeichnisplan ausfuehren. Rueckgabe: (kopiert, verschoben,
    uebersprungen, fehler)."""
    destdir = plan["dest"]
    n_copy = n_move = n_skip = n_err = 0

    if not args.dry_run:
        os.makedirs(destdir, exist_ok=True)

    for group, typen, bleiben, (neue_zeit, shift, zuschlag) in zip(
            plan["groups"], plan["typen"], plan["bleiben"], plan["schedule"]):
        kopf = "[Laufzeit {}]".format(laufzeit_text())
        if args.rekursiv:
            kopf += " " + plan.get("relpfad", ".")
        FORT.leeren()
        print(kopf)

        if bereits_erledigt(destdir, group[0]["stem"]):
            print("Serie BurstGroupID={} | Startdatei {} -- bereits abgelegt, "
                  "uebersprungen".format(group[0]["gid"], group[0]["name"]))
            log("serie-uebersprungen gid={} dir={} start={} grund=bereits-abgelegt"
                .format(group[0]["gid"], plan["dir"], group[0]["name"]))
            n_skip += len(group)
            print()
            continue
        start, ops = plan_group(group, destdir, args.ev_rounding, typen, bleiben)
        if neue_zeit is None:
            zeit = "?"
        elif shift > 0:
            zeit = "{} (statt {}, +{:g} s)".format(
                neue_zeit.strftime("%Y-%m-%d %H:%M:%S"),
                start["dt"].strftime("%H:%M:%S"), shift)
        else:
            zeit = neue_zeit.strftime("%Y-%m-%d %H:%M:%S")
        if zuschlag > 0:
            zeit += " | Langzeitbelichtung {:g} s -> naechste Serie +{:g} s".format(
                zuschlag, zuschlag)
        print("Serie BurstGroupID={} | {} | Startdatei {} | {} Bilder | {}"
              .format(start["gid"], typ_text(typen), start["name"], len(group), zeit))
        log("serie gid={} dir={} typ={} start={} bilder={} zeit={} shift={:g}"
            .format(start["gid"], plan["dir"], typ_kurz(typen), start["name"],
                    len(group),
                    neue_zeit.strftime("%Y-%m-%dT%H:%M:%S") if neue_zeit else "-",
                    shift))
        if start.get("schaerfe") is not None:
            print("  Schaerfe: {} -- {} Bild(er) bleiben liegen (Toleranz {:g}%)"
                  .format(", ".join("{}={}".format(r["name"], int(round(r["schaerfe"])))
                                    for r in group),
                          bleiben, args.schaerfe_toleranz))

        ziele_start, ziele_folge = [], []
        for nr, (rec, target, action) in enumerate(ops):
            eimer = ziele_start if nr == 0 else ziele_folge
            marker = "kopieren" if action == "copy" else "verschieben"
            aktion_name = "kopiert" if action == "copy" else "verschoben"
            if os.path.exists(target):
                print("  ! ZIEL EXISTIERT, uebersprungen: {}".format(os.path.basename(target)))
                log("ziel-existiert gid={} quelle={} ziel={}".format(
                    start["gid"], rec["path"], target))
                n_skip += 1
                continue
            print("  {:<11} {:<26} -> {}".format(marker, rec["name"], os.path.basename(target)))
            if args.dry_run:
                log("geplant-{} gid={} quelle={} ziel={}".format(
                    aktion_name, start["gid"], rec["path"], target))
                eimer.append(target)
                continue
            try:
                if action == "copy":
                    shutil.copy2(rec["path"], target)
                    n_copy += 1
                else:
                    shutil.move(rec["path"], target)
                    n_move += 1
                log("{} gid={} quelle={} ziel={}".format(
                    aktion_name, start["gid"], rec["path"], target))
                eimer.append(target)
            except OSError as exc:
                print("  ! FEHLER: {}".format(exc))
                log("fehler gid={} quelle={} ziel={} grund={}".format(
                    start["gid"], rec["path"], target, exc))
                n_err += 1

        if args.set_time and (ziele_start or ziele_folge) and neue_zeit:
            folgezeit = neue_zeit + timedelta(seconds=args.folge_offset)
            for ziele, zeitpunkt, was in ((ziele_start, neue_zeit, "Startbild  "),
                                          (ziele_folge, folgezeit, "Folgebilder")):
                if not ziele:
                    continue
                print("  Zeit {} -> {} ({} Datei(en))"
                      .format(was, zeitpunkt.strftime("%Y:%m:%d %H:%M:%S"), len(ziele)))
                if args.dry_run:
                    continue
                ok, err = set_times(ziele, zeitpunkt, start["subsec"], args.exiftool)
                if ok:
                    log("zeit-gesetzt gid={} zeit={} dateien={}".format(
                        start["gid"], zeitpunkt.strftime("%Y-%m-%dT%H:%M:%S"),
                        len(ziele)))
                else:
                    print("  ! exiftool (Zeit): {}".format(err))
                    log("zeit-fehler gid={} grund={}".format(start["gid"], err))
                    n_err += 1
        elif args.set_time and (ziele_start or ziele_folge) and not neue_zeit:
            print("  ! Startdatei hat kein DateTimeOriginal -- Zeit nicht angepasst.")
        print()

    if args.verbose and plan["skipped"]:
        print("Uebersprungene Dateien (keine/zu kleine Serie):")
        for r in sorted(plan["skipped"], key=lambda x: x["name"]):
            print("  {} (BurstGroupID={})".format(r["name"], r["gid"]))
        print()

    return n_copy, n_move, n_skip, n_err


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="breihen.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Belichtungsreihen (Nikon BurstGroupID) sortieren und umbenennen.",
        epilog=__doc__,
    )
    p.add_argument("startverzeichnis", nargs="?", default=".",
                   help="Verzeichnis mit den Bilddateien (Vorgabe: aktuelles Verzeichnis)")
    p.add_argument("--rekursiv", action="store_true",
                   help="Auch alle Unterverzeichnisse bearbeiten (jeweils mit eigenem "
                        "Unterverzeichnis '{}'). Ausgelassen werden die selbst "
                        "erzeugten Zielverzeichnisse sowie Verzeichnisse, deren Name "
                        "mit {} beginnt. Vorgabe: aus."
                        .format("breihen", "/".join(SKIP_DIR_ANZEIGE)))
    p.add_argument("--dest", default="breihen",
                   help="Name des Unterverzeichnisses (Vorgabe: breihen)")
    p.add_argument("--typen", default="ae", metavar="LISTE",
                   help="Welche Bracketing-Arten bearbeitet werden, kommagetrennt aus "
                        "ae (Belichtungsreihe), flash (Blitzreihe), wb (Weissabgleich), "
                        "adl (Active-D-Lighting) und keine (alle Bilder gleich "
                        "aufgenommen) -- oder 'alle'. Vorgabe: ae")
    p.add_argument("--allbracketing", action="store_true",
                   help="Alle Serien bearbeiten, unabhaengig von der Bracketing-Art "
                        "(gleichbedeutend mit --typen alle)")
    p.add_argument("--keine-schaerfe", dest="schaerfe", action="store_false",
                   help="Serien vom Typ 'keine' NICHT nach Schaerfe ordnen; dann "
                        "bleibt wie sonst das chronologisch erste Bild liegen")
    p.add_argument("--schaerfe-toleranz", type=float, default=5.0, metavar="PROZENT",
                   help="Bilder, die weniger als PROZENT unter dem schaerfsten liegen, "
                        "bleiben ebenfalls im Originalverzeichnis (Vorgabe: 5)")
    p.add_argument("--schaerfe-bericht", action="store_true",
                   help="Nur die Schaerfewerte je Serie ausgeben und beenden -- "
                        "nichts kopieren, verschieben oder aendern")
    p.add_argument("--min-size", type=int, default=2,
                   help="Mindestanzahl Bilder je Serie (Vorgabe: 2)")
    p.add_argument("--max-gap", type=float, default=0.0, metavar="SEK",
                   help="Serie zerlegen, wenn zwischen zwei Aufnahmen mehr als SEK "
                        "Sekunden liegen (0 = aus)")
    p.add_argument("--min-abstand", type=float, default=32.0, metavar="SEK",
                   help="Mindestabstand der Startzeitpunkte zweier Serien; "
                        "zu dicht liegende Serien werden nach hinten geschoben "
                        "(Vorgabe: 32, 0 = aus)")
    p.add_argument("--lange-belichtung", type=float, default=14.0, metavar="SEK",
                   help="Schwelle fuer Langzeitbelichtung: enthaelt eine Serie ein Bild "
                        "mit laengerer Belichtungszeit, wird dieser Wert zusaetzlich "
                        "zum Mindestabstand vor die naechste Serie gelegt (Vorgabe: 14)")
    p.add_argument("--folge-offset", type=float, default=1.0, metavar="SEK",
                   help="Zeitversatz der Folgebilder gegenueber dem Startbild "
                        "derselben Serie (Vorgabe: 1)")
    p.add_argument("--ev-rounding", choices=["truncate", "round"], default="truncate",
                   help="EV-Nachkommastelle abschneiden (2/3 -> 0.6, Vorgabe) "
                        "oder runden (2/3 -> 0.7)")
    p.add_argument("--keine-zeitanpassung", dest="set_time", action="store_false",
                   help="EXIF-/Dateizeiten nicht auf die Startdatei angleichen")
    p.add_argument("--reserve-prozent", type=float, default=2.0, metavar="PROZENT",
                   help="Anteil der Gesamtkapazitaet des Dateisystems, der zusaetzlich "
                        "zum Schreibbedarf frei bleiben muss (Vorgabe: 2)")
    p.add_argument("--rechte-ignorieren", dest="rechte_pruefen", action="store_false",
                   help="Fehler der Rechtepruefung nur als Warnung ausgeben statt "
                        "abzubrechen (Notnagel bei exotischen Dateisystemen)")
    p.add_argument("--logfile", default=None, metavar="PFAD",
                   help="Protokolldatei, wird bei jedem Aufruf angefuegt "
                        "(Vorgabe: breihen.log im Startverzeichnis)")
    p.add_argument("--kein-log", dest="log", action="store_false",
                   help="kein Protokoll schreiben")
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="Nur anzeigen, was passieren wuerde")
    p.add_argument("--exiftool", default="exiftool", help="Pfad zu exiftool")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Auch uebersprungene Dateien und Verzeichnisse auflisten")
    args = p.parse_args(argv)

    global START_ZEIT
    START_ZEIT = time.monotonic()

    if args.schaerfe_bericht:
        args.schaerfe = True

    if args.allbracketing or args.typen.strip().lower() in ("alle", "all"):
        args.typen = set(ALLE_TYPEN)
    else:
        args.typen = set(t.strip().lower() for t in args.typen.split(",") if t.strip())
        unbekannt = args.typen - set(ALLE_TYPEN)
        if unbekannt:
            p.error("unbekannte Bracketing-Art(en): {} -- erlaubt sind: {}, alle"
                    .format(", ".join(sorted(unbekannt)), ", ".join(ALLE_TYPEN)))
        if not args.typen:
            p.error("--typen darf nicht leer sein")

    if shutil.which(args.exiftool) is None:
        p.error("exiftool nicht gefunden. "
                "Installation: sudo apt install libimage-exiftool-perl")

    startdir = os.path.abspath(args.startverzeichnis)
    if not os.path.isdir(startdir):
        p.error("Startverzeichnis existiert nicht: " + startdir)
    args.startdir = startdir          # Bezug fuer die relative Pfadanzeige

    if args.log:
        log_oeffnen(args.logfile or os.path.join(startdir, "breihen.log"))
    log("start dir={} modus={} typen={} rekursiv={} argv={}".format(
        startdir,
        "probelauf" if args.dry_run else
        ("bericht" if args.schaerfe_bericht else "echt"),
        ",".join(sorted(args.typen)), int(args.rekursiv),
        " ".join(argv if argv is not None else sys.argv[1:])))

    # ----- Phase 1: nur lesen, planen ---------------------------------------
    verzeichnisse, uebersprungene_verz = collect_dirs(startdir, args.dest, args.rekursiv)
    print("Startverzeichnis: {}".format(startdir))
    if args.rekursiv:
        print("Rekursiv: {} Verzeichnis(se) durchsucht, {} ausgelassen ({} / {}*)"
              .format(len(verzeichnisse), len(uebersprungene_verz),
                      args.dest, "* / ".join(SKIP_DIR_ANZEIGE)))
        if args.verbose:
            for d in uebersprungene_verz:
                print("  ausgelassen: {}".format(d))

    plaene = []
    for nr, d in enumerate(verzeichnisse, 1):
        FORT.zeige("durchsuche Verzeichnis {}/{}: {}".format(
            nr, len(verzeichnisse), d))
        pl = analysiere(d, args)
        if pl:
            plaene.append(pl)
            log("verzeichnis dir={} dateien={} serien={} uebergangen={} ohne_gid={}"
                .format(pl["dir"], len(pl["files"]), len(pl["groups"]),
                        len(pl["ignoriert"]), len(pl["skipped"])))
    FORT.leeren()
    aktiv = [pl for pl in plaene if pl["groups"]]

    n_files = sum(len(pl["files"]) for pl in plaene)
    n_serien = sum(len(pl["groups"]) for pl in aktiv)
    n_ohne = sum(len(pl["skipped"]) for pl in plaene)
    n_shift = sum(1 for pl in aktiv for _, sh, _z in pl["schedule"] if sh > 0)
    n_lang = sum(1 for pl in aktiv for _, _sh, z in pl["schedule"] if z > 0)

    print("Bearbeitete Bracketing-Arten: {}"
          .format(", ".join(TYP_LABEL[t] for t in ALLE_TYPEN if t in args.typen)))
    print("Gefunden: {} Bilddatei(en), {} passende Serie(n) in {} Verzeichnis(sen), "
          "{} Datei(en) ohne verwertbare BurstGroupID."
          .format(n_files, n_serien, len(aktiv), n_ohne))

    # Uebersicht der uebergangenen Serien -- damit sichtbar bleibt, was auf der
    # Karte sonst noch liegt und mit welchem Schalter man es erreichen wuerde.
    ignoriert_nach_typ = {}
    for pl in plaene:
        for g, typen in pl["ignoriert"]:
            eintrag = ignoriert_nach_typ.setdefault(typ_text(typen), [0, 0])
            eintrag[0] += 1
            eintrag[1] += len(g)
    if ignoriert_nach_typ:
        print("Uebergangen (unveraendert liegen geblieben):")
        for text in sorted(ignoriert_nach_typ):
            serien, bilder = ignoriert_nach_typ[text]
            print("  {:<24} {} Serie(n), {} Bild(er)".format(text, serien, bilder))
        print("  -> mit --allbracketing oder --typen ... einbeziehen")
        if args.verbose:
            for pl in plaene:
                for g, typen in pl["ignoriert"]:
                    hinweis = g[0].get("bracketset")
                    print("     {} ({}, {} Bilder{})"
                          .format(os.path.join(pl["dir"], g[0]["name"]), typ_text(typen),
                                  len(g), ", Kamera-Menue: " + hinweis if hinweis else ""))

    if not aktiv:
        print("Keine Belichtungsreihe (BurstGroupID) gefunden -- nichts zu tun.")
        if args.verbose:
            for pl in plaene:
                for r in pl["skipped"]:
                    print("  uebersprungen: {} (BurstGroupID={})".format(r["path"], r["gid"]))
        return 0

    if args.schaerfe and not schaerfe_verfuegbar() and any(
            not t for pl in aktiv for t in pl["typen"]):
        print("HINWEIS: numpy/Pillow fehlen -- Schaerfemessung uebersprungen.\n"
              "         sudo apt install libimage-exiftool-perl python3-scipy "
              "python3-pil libraw-bin\n")

    if args.schaerfe_bericht:
        gab_es = False
        for pl in plaene:
            for g, info, bleiben in pl.get("schaerfe", []):
                gab_es = True
                print("\nSerie BurstGroupID={} in {} ({} Bilder, Messfenster: {})"
                      .format(g[0]["gid"], pl["dir"], len(g), info))
                best = g[0].get("schaerfe") or 0.0
                for r in g:
                    wert = r.get("schaerfe")
                    if wert is None:
                        print("  {:<28} --".format(r["name"]))
                        continue
                    abw = 0.0 if best <= 0 else (best - wert) / best * 100.0
                    print("  Rang {} {:<26} {:8.1f}   {:5.1f}% unter dem besten   {}"
                          .format(r.get("rang", "?"), r["name"], wert, abw,
                                  "bleibt liegen" if abw <= args.schaerfe_toleranz
                                  else "wird verschoben"))
        if not gab_es:
            print("\nKeine Serie vom Typ 'keine' zum Messen gefunden "
                  "(mit --typen keine oder --allbracketing einbeziehen).")
        print("\nNur Bericht -- es wurde nichts veraendert.")
        log("ende modus=bericht laufzeit={}".format(laufzeit_text()))
        return 0

    if args.min_abstand > 0:
        print("Zeitschema: Startbild T, Folgebilder T+{:g} s; Mindestabstand der "
              "Serien-Startzeiten {:g} s"
              .format(args.folge_offset, args.min_abstand))
        print("            (+ Belichtungszeit, wenn eine Serie laenger als {:g} s "
              "belichtet -- betrifft {} Serie(n))".format(args.lange_belichtung, n_lang))
        print("            {} Serie(n) zeitlich verschoben.".format(n_shift))
    print()

    # ----- Phase 2: Rechte und Platz pruefen, BEVOR etwas geschrieben wird ---
    #       Die Pruefung legt nur temporaere Testdateien an und raeumt sie weg.
    probleme = preflight(aktiv, args.reserve_prozent)
    if probleme:
        titel = ("ABBRUCH: Rechte- bzw. Speicherplatzpruefung fehlgeschlagen"
                 if args.rechte_pruefen
                 else "WARNUNG: Rechte- bzw. Speicherplatzpruefung fehlgeschlagen")
        sys.stdout.flush()
        print(titel + ":", file=sys.stderr)
        for f in probleme:
            print("  - " + f, file=sys.stderr)
            log("preflight-fehler grund={}".format(f))
        if args.rechte_pruefen:
            print("\nEs wurde nichts kopiert, verschoben oder veraendert.", file=sys.stderr)
            sys.stderr.flush()
            log("abbruch grund=preflight laufzeit={}".format(laufzeit_text()))
            return 2
        print("  (wird auf Wunsch ignoriert -- Fortsetzung mit --rechte-ignorieren)\n",
              file=sys.stderr)
    else:
        print("Pruefung bestanden: Rechte (lesen, anlegen, schreiben, umbenennen, "
              "Dateidatum setzen, loeschen)\n"
              "                    und Speicherplatz (inkl. {:g}% Reserve) fuer "
              "{} Verzeichnis(se).\n".format(args.reserve_prozent, len(aktiv)))

    # ----- Phase 3: ausfuehren ----------------------------------------------
    n_copy = n_move = n_skip = n_err = 0
    for pl in aktiv:
        if len(aktiv) > 1 or args.rekursiv:
            print("=== {}  --  {} Bilddatei(en), {} Serie(n)"
                  .format(pl["dir"], len(pl["files"]), len(pl["groups"])))
        c, m, s, e = verarbeite(pl, args)
        n_copy += c; n_move += m; n_skip += s; n_err += e

    if args.dry_run:
        print("Probelauf -- es wurde nichts veraendert.")
    else:
        print("Fertig: {} kopiert, {} verschoben, {} uebersprungen, {} Fehler."
              .format(n_copy, n_move, n_skip, n_err))
    log("ende kopiert={} verschoben={} uebersprungen={} fehler={} laufzeit={}"
        .format(n_copy, n_move, n_skip, n_err, laufzeit_text()))
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
