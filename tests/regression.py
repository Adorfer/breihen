#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regressionstests fuer breihen.py.

Aufruf (aus dem Repo-Verzeichnis oder von ueberall):

    python3 tests/regression.py                 # alle Tests
    python3 tests/regression.py -k paar         # nur Tests, deren Name "paar" enthaelt
    python3 tests/regression.py --behalten      # Arbeitsverzeichnis nicht loeschen

Braucht zusaetzlich zu den Laufzeit-Abhaengigkeiten ImageMagick (magick) fuer
die synthetischen Testbilder:  sudo apt install imagemagick

Prinzip: Echte Nikon-MakerNotes (BurstGroupID usw.) lassen sich nicht in ein
selbst erzeugtes JPEG schreiben. Die Tests erzeugen deshalb Bilder mit
ImageMagick, setzen Zeit und Belichtung per exiftool und injizieren
BurstGroupID, Seriennummer und Bracket-Werte, indem breihen.read_metadata
umhuellt wird. Alles andere -- Gruppieren, Messen, Kopieren, Verschieben,
Zeiten schreiben -- laeuft echt.

Exit-Code 0 = alles bestanden, 1 = mindestens ein Fehlschlag, 2 = Werkzeug fehlt.
"""

import argparse
import contextlib
import importlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import breihen  # noqa: E402

ARBEIT = None          # Temp-Verzeichnis, wird in main() angelegt
BASIS = None           # Ausgangsbild fuer alle Testbilder
META = {}              # (verzeichnis, dateiname) -> injizierte Nikon-Werte
ERGEBNISSE = []
TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


# ---------------------------------------------------------------------------
# Hilfsmittel
# ---------------------------------------------------------------------------

def bild(d, name, zeit, blur=None, meta=None, kaputt=False, belichtung=None):
    """Testbild anlegen. .jpg/.jpeg = echtes JPEG, .tif = echtes TIFF,
    alles andere (z.B. .NEF) = JPEG-Inhalt mit dieser Endung -- reicht zum
    Gruppieren und Umbenennen, exiftool kann es aber nicht beschreiben."""
    fp = os.path.join(d, name)
    ext = os.path.splitext(name)[1].lower()
    zeitargs = ["-DateTimeOriginal=" + zeit] + (
        ["-ExposureTime=%s" % belichtung] if belichtung else [])
    if ext in (".jpg", ".jpeg"):
        subprocess.run(["magick", BASIS] + (["-blur", "0x%s" % blur] if blur else [])
                       + ["-quality", "90", fp], check=True)
        subprocess.run(["exiftool", "-q", "-q", "-overwrite_original"] + zeitargs + [fp],
                       check=True)
        if kaputt:
            with open(fp, "r+b") as fh:
                fh.truncate(600)
    elif ext in (".tif", ".tiff"):
        subprocess.run(["magick", BASIS, "-resize", "300x200", fp], check=True)
        subprocess.run(["exiftool", "-q", "-q", "-overwrite_original"] + zeitargs + [fp],
                       check=True)
    else:
        tmp = fp + ".tmp.jpg"
        subprocess.run(["magick", BASIS, "-quality", "90", tmp], check=True)
        subprocess.run(["exiftool", "-q", "-q", "-overwrite_original"] + zeitargs + [tmp],
                       check=True)
        os.rename(tmp, fp)
    META[(d, name)] = meta or {}


def _fake_read_metadata(orig):
    def fake(paths, exiftool="exiftool", fortschritt=None):
        recs = orig(paths, exiftool, fortschritt)
        for r in recs:
            m = META.get((os.path.dirname(r["path"]), r["name"]), {})
            r["gid"] = m.get("gid", 0)
            r["ev"] = m.get("ev", 0.0)
            r["var"] = {"ae": m.get("ev", 0.0), "flash": None, "wb": None, "adl": 3}
            if "serial" in m:
                r["serial"] = m["serial"]
        return recs
    return fake


def lauf(d, *args, patch=None):
    """breihen.main() im selben Prozess; liefert (exit, stdout, stderr).
    patch(modul) darf nach dem Neuladen einzelne Funktionen ersetzen."""
    importlib.reload(breihen)
    breihen.read_metadata = _fake_read_metadata(breihen.read_metadata)
    if patch:
        patch(breihen)
    o, e = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
            rc = breihen.main([d, "--kein-log"] + list(args))
    except SystemExit as se:
        rc = se.code
    except Exception:
        rc = "EXCEPTION"
        e.write(traceback.format_exc())
    return rc, o.getvalue(), e.getvalue()


def neu(name):
    d = os.path.join(ARBEIT, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    return d


def ls(d):
    return sorted(f for f in os.listdir(d) if not f.startswith("."))


def check(name, ok, info=""):
    ERGEBNISSE.append((name, bool(ok)))
    zeile = ("PASS  " if ok else "FAIL  ") + name
    if info and not ok:
        zeile += "   -- " + str(info)[-400:]
    print(zeile)


def zeiten(d):
    out = subprocess.run(["exiftool", "-q", "-T", "-FileName", "-DateTimeOriginal", d],
                         capture_output=True, text=True).stdout.strip().splitlines()
    return dict(l.split("\t") for l in out if "\t" in l)


# ---------------------------------------------------------------------------
# Tests: Grundverhalten
# ---------------------------------------------------------------------------

@test
def basis_ae_und_schaerfe():
    d = neu("basis")
    for i, ev in enumerate([0.0, -1 / 3, 2 / 3]):
        bild(d, "AE%02d.jpeg" % i, "2024:02:14 09:00:0%d" % i, meta=dict(gid=100, ev=ev))
    bild(d, "SF00.jpeg", "2024:02:14 09:05:00", blur="2.0", meta=dict(gid=900))
    bild(d, "SF01.jpeg", "2024:02:14 09:05:01", meta=dict(gid=900))
    bild(d, "SF02.jpeg", "2024:02:14 09:05:02", blur="3.0", meta=dict(gid=900))
    rc, o, e = lauf(d, "--allbracketing")
    check("Basis: exit 0", rc == 0, str(rc) + e)
    check("Basis: es bleiben AE00 und das schaerfste SF01", ls(d) == ["AE00.jpeg", "SF01.jpeg", "breihen"], ls(d))
    z = ls(os.path.join(d, "breihen"))
    check("Basis: AE-Namensschema", "AE00_N1G3_(B+0).jpeg" in z and "AE00_N2_(B-0.3)_AE01.jpeg" in z, z)
    check("Basis: Schaerfe-Namensschema", any(n.startswith("SF01_N1G3_(S1_") for n in z), z)
    t = zeiten(os.path.join(d, "breihen"))
    check("Basis: Zeiten T / T+1", t.get("AE00_N1G3_(B+0).jpeg") == "2024:02:14 09:00:00"
          and t.get("AE00_N3_(B+0.6)_AE02.jpeg") == "2024:02:14 09:00:01", t)


@test
def vorgabe_nur_ae():
    d = neu("vorgabe")
    for i, ev in enumerate([0.0, -1.0, 1.0]):
        bild(d, "AE%02d.jpeg" % i, "2024:02:14 09:00:0%d" % i, meta=dict(gid=100, ev=ev))
    for i in range(3):
        bild(d, "SF%02d.jpeg" % i, "2024:02:14 09:05:0%d" % i, meta=dict(gid=900))
    lauf(d)
    check("Vorgabe --typen ae: Schaerfe-Serie bleibt unangetastet",
          ls(d) == ["AE00.jpeg", "SF00.jpeg", "SF01.jpeg", "SF02.jpeg", "breihen"], ls(d))


@test
def mindestabstand_kaskade():
    d = neu("abstand")
    for k, b in enumerate("ABC"):
        for i in range(3):
            bild(d, "%s%02d.jpeg" % (b, i), "2024:02:14 09:00:%02d" % (k * 5 + i),
                 meta=dict(gid=100 + k, ev=[0.0, -1.0, 1.0][i]))
    lauf(d)
    t = zeiten(os.path.join(d, "breihen"))
    check("Mindestabstand 32 s, kaskadierend",
          t.get("A00_N1G3_(B+0).jpeg", "").endswith("09:00:00")
          and t.get("B00_N1G3_(B+0).jpeg", "").endswith("09:00:32")
          and t.get("C00_N1G3_(B+0).jpeg", "").endswith("09:01:04"), t)


# ---------------------------------------------------------------------------
# Tests: Serienerkennung (BurstGroupID-Umlauf, Bodies, Langzeit)
# ---------------------------------------------------------------------------

@test
def zwei_bodies_gleiche_id():
    d = neu("bodies")
    for i, ev in enumerate([0.0, -1.0, 1.0]):
        bild(d, "A%02d.jpeg" % i, "2024:02:14 09:00:0%d" % i, meta=dict(gid=7, ev=ev, serial="1111"))
        bild(d, "B%02d.jpeg" % i, "2024:02:14 09:00:1%d" % i, meta=dict(gid=7, ev=ev, serial="2222"))
    rc, o, e = lauf(d, "-n")
    check("Zwei Bodies, gleiche ID: zwei Serien", o.count("Serie BurstGroupID=") == 2,
          o.count("Serie BurstGroupID="))


@test
def id_umlauf_trennt():
    d = neu("umlauf")
    for i, ev in enumerate([0.0, -1.0, 1.0]):
        bild(d, "A%02d.jpeg" % i, "2024:02:14 09:00:0%d" % i, meta=dict(gid=5, ev=ev))
        bild(d, "B%02d.jpeg" % i, "2024:02:15 12:00:0%d" % i, meta=dict(gid=5, ev=ev))
    rc, o, e = lauf(d, "-n")
    check("ID-Umlauf: gleiche ID einen Tag spaeter -> zwei Serien",
          o.count("Serie BurstGroupID=") == 2, o.count("Serie BurstGroupID="))


@test
def langzeit_bleibt_eine_serie():
    d = neu("langzeit")
    for i, ev in enumerate([0.0, -1.0, 1.0]):     # 30 s + Rauschunterdrueckung: 62 s Abstand
        bild(d, "L%02d.jpeg" % i, "2024:02:14 09:%02d:%02d" % ((i * 62) // 60, (i * 62) % 60),
             meta=dict(gid=8, ev=ev), belichtung=30)
    rc, o, e = lauf(d, "-n")
    check("Langzeit 30 s + LENR: bleibt EINE Serie", o.count("Serie BurstGroupID=") == 1,
          o.count("Serie BurstGroupID="))


@test
def kurz_mit_luecke_trennt():
    d = neu("kurzluecke")
    for i, ev in enumerate([0.0, -1.0, 1.0]):
        bild(d, "Q%02d.jpeg" % i, "2024:02:14 09:%02d:%02d" % ((i * 62) // 60, (i * 62) % 60),
             meta=dict(gid=9, ev=ev), belichtung="1/250")
    rc, o, e = lauf(d, "-n")
    check("Gegenprobe: 1/250 s mit 62 s Luecken -> getrennt", o.count("Serie BurstGroupID=") == 0,
          o.count("Serie BurstGroupID="))


# ---------------------------------------------------------------------------
# Tests: RAW+JPEG-Paare
# ---------------------------------------------------------------------------

@test
def paar_raw_jpeg():
    d = neu("paare")
    for i, ev in enumerate([0.0, -1.0, 1.0]):
        for ext in (".JPG", ".NEF"):
            bild(d, "DSC_%04d%s" % (i, ext), "2024:02:14 09:00:0%d" % i, meta=dict(gid=100, ev=ev))
    lauf(d)
    z = ls(os.path.join(d, "breihen"))
    check("Paar: beide Startdateien bleiben liegen", ls(d) == ["DSC_0000.JPG", "DSC_0000.NEF", "breihen"], ls(d))
    check("Paar: G zaehlt Aufnahmen (G3)",
          "DSC_0000_N1G3_(B+0).JPG" in z and "DSC_0000_N1G3_(B+0).NEF" in z, z)
    check("Paar: Folgeaufnahme mit gleichem Namen",
          "DSC_0000_N2_(B-1)_DSC_0001.JPG" in z and "DSC_0000_N2_(B-1)_DSC_0001.NEF" in z, z)


@test
def paar_zeiten_gleich():
    d = neu("paarezeit")
    for i, ev in enumerate([0.0, -1.0, 1.0]):
        for ext in (".JPG", ".TIF"):
            bild(d, "DSC_%04d%s" % (i, ext), "2024:02:14 09:00:0%d" % i, meta=dict(gid=100, ev=ev))
    rc, o, e = lauf(d)
    check("Paar JPG+TIF: exit 0", rc == 0, str(rc) + o[-300:])
    z = zeiten(os.path.join(d, "breihen"))
    soll = {"DSC_0000_N1G3_(B+0)": "09:00:00", "DSC_0000_N2_(B-1)_DSC_0001": "09:00:01",
            "DSC_0000_N3_(B+1)_DSC_0002": "09:00:01"}
    check("Paar JPG+TIF: Begleitdatei bekommt dieselbe Zeit",
          all(z.get(k + x, "").endswith(v) for k, v in soll.items() for x in (".JPG", ".TIF")), z)


@test
def paar_in_schaerfe_serie():
    d = neu("paareschaerfe")
    for i, bl in enumerate(["2.5", None, "3.5"]):
        bild(d, "K%02d.JPG" % i, "2024:02:14 09:00:0%d" % i, blur=bl, meta=dict(gid=900))
        bild(d, "K%02d.NEF" % i, "2024:02:14 09:00:0%d" % i, meta=dict(gid=900))
    lauf(d, "--typen", "keine")
    z = ls(os.path.join(d, "breihen"))
    check("Schaerfe-Serie mit Paaren: JPG+NEF der schaerfsten bleiben",
          ls(d) == ["K01.JPG", "K01.NEF", "breihen"], ls(d))
    check("Schaerfe-Serie mit Paaren: NEF traegt denselben S-Rang",
          any(n.startswith("K01_N1G3_(S1_") and n.endswith(".NEF") for n in z), z)


# ---------------------------------------------------------------------------
# Tests: Fehlerfaelle und Wiederholungslaeufe
# ---------------------------------------------------------------------------

@test
def schaerfe_kaputtes_jpeg():
    d = neu("kaputt")
    bild(d, "K00.jpeg", "2024:02:14 09:00:00", meta=dict(gid=900))
    bild(d, "K01.jpeg", "2024:02:14 09:00:01", meta=dict(gid=900), kaputt=True)
    bild(d, "K02.jpeg", "2024:02:14 09:00:02", blur="2", meta=dict(gid=900))
    rc, o, e = lauf(d, "--typen", "keine", "-n")
    check("Abgeschnittenes JPEG mitten in Schaerfe-Serie: kein Absturz",
          rc in (0, 1) and "Traceback" not in e, str(rc) + e)


@test
def startkopie_scheitert():
    d = neu("startkopie")
    for i, ev in enumerate([0.0, -1 / 3, 2 / 3]):
        bild(d, "S%02d.jpeg" % i, "2024:02:14 09:00:0%d" % i, meta=dict(gid=100, ev=ev))
    echt = shutil.copy2

    def platte_voll(src, dst, *a, **k):
        if os.path.basename(src) == "S00.jpeg":
            raise OSError(28, "No space left on device")
        return echt(src, dst, *a, **k)
    shutil.copy2 = platte_voll
    try:
        lauf(d)
    finally:
        shutil.copy2 = echt
    check("Startkopie scheitert: Folgebilder bleiben liegen",
          ls(d)[:3] == ["S00.jpeg", "S01.jpeg", "S02.jpeg"], ls(d))


@test
def kopie_atomar_bei_ctrl_c():
    d = neu("atomar")
    q = os.path.join(d, "q.jpg")
    with open(q, "wb") as fh:
        fh.write(b"x" * 100000)
    echt = shutil.copy2

    def ctrl_c(src, dst, *a, **k):
        with open(dst, "wb") as fh:
            fh.write(b"x" * 3000)
        raise KeyboardInterrupt
    shutil.copy2 = ctrl_c
    try:
        breihen.kopieren_atomar(q, os.path.join(d, "Z_N1G3_(B+0).jpg"))
        weiter = False
    except KeyboardInterrupt:
        weiter = True
    finally:
        shutil.copy2 = echt
    check("Ctrl-C in der Kopie: kein halber Zielname, Temp-Datei weg",
          weiter and sorted(os.listdir(d)) == ["q.jpg"], sorted(os.listdir(d)))


@test
def klammerpfad_zweitlauf():
    d = neu("Fotos [2025]")
    bild(d, "K00.jpeg", "2024:02:14 09:00:00", meta=dict(gid=900))
    bild(d, "K01.jpeg", "2024:02:14 09:00:01", blur="0.1", meta=dict(gid=900))
    bild(d, "K02.jpeg", "2024:02:14 09:00:02", blur="3", meta=dict(gid=900))
    lauf(d, "--typen", "keine")
    vorher = ls(os.path.join(d, "breihen"))
    lauf(d, "--typen", "keine")
    check("Pfad mit [ ]: zweiter Lauf legt nichts neu an",
          vorher == ls(os.path.join(d, "breihen")), (vorher, ls(os.path.join(d, "breihen"))))


@test
def zweitlauf_anderer_bester():
    d = neu("zweitlauf")
    bild(d, "K00.jpeg", "2024:02:14 09:00:00", meta=dict(gid=900))
    bild(d, "K01.jpeg", "2024:02:14 09:00:01", blur="0.15", meta=dict(gid=900))
    bild(d, "K02.jpeg", "2024:02:14 09:00:02", blur="3", meta=dict(gid=900))
    lauf(d, "--typen", "keine")
    liegen, ziel = ls(d), ls(os.path.join(d, "breihen"))
    # K00 unschaerfer machen -> im zweiten Lauf gewinnt K01
    bild(d, "K00.jpeg", "2024:02:14 09:00:00", blur="0.3", meta=dict(gid=900))
    lauf(d, "--typen", "keine")
    check("Zweitlauf mit anderer Rangfolge: nichts angelegt, nichts verschoben",
          ls(d) == liegen and ls(os.path.join(d, "breihen")) == ziel, (liegen, ls(d)))


@test
def unvollstaendige_serie():
    d = neu("unvoll")
    for i, ev in enumerate([0.0, -1 / 3, 2 / 3]):
        bild(d, "U%02d.jpeg" % i, "2024:02:14 09:00:0%d" % i, meta=dict(gid=100, ev=ev))
    lauf(d)
    b = os.path.join(d, "breihen")           # Abbruch simulieren: U02 nie verschoben
    shutil.move(os.path.join(b, "U00_N3_(B+0.6)_U02.jpeg"), os.path.join(d, "U02.jpeg"))
    rc, o, e = lauf(d)
    check("Halbfertige Serie: als UNVOLLSTAENDIG gemeldet, exit 1",
          "UNVOLLSTAENDIG" in o and rc == 1, str(rc) + o[-300:])


# ---------------------------------------------------------------------------
# Tests: --zeiten-nachziehen
# ---------------------------------------------------------------------------

def _zeitschreiben_scheitert_fuer(praefix):
    """patch-Funktion: set_times scheitert fuer Dateien mit diesem Namenspraefix."""
    def patch(modul):
        echt = modul.set_times

        def set_times(targets, dt, subsec, exiftool="exiftool"):
            if any(os.path.basename(t).startswith(praefix) for t in targets):
                return False, "simuliert: Netzlaufwerk weg"
            return echt(targets, dt, subsec, exiftool)
        modul.set_times = set_times
    return patch


def _zwei_serien_b_scheitert(name, ext=".jpeg", begleiter=None):
    """A und B zu dicht (B wird auf 09:00:32 geplant); Zeitschreiben fuer B scheitert."""
    d = neu(name)
    for k, b in enumerate("AB"):
        for i, ev in enumerate([0.0, -1.0, 1.0]):
            for e in [ext] + ([begleiter] if begleiter else []):
                bild(d, "%s%02d%s" % (b, i, e), "2024:02:14 09:00:%02d" % (k * 5 + i),
                     meta=dict(gid=100 + k, ev=ev))
    rc, o, e = lauf(d, patch=_zeitschreiben_scheitert_fuer("B00_"))
    return d, rc


def _mtime_sekunde(p):
    from datetime import datetime
    return datetime.fromtimestamp(os.stat(p).st_mtime).strftime("%Y:%m:%d %H:%M:%S")


@test
def nachziehen_repariert():
    d, rc = _zwei_serien_b_scheitert("nachziehen")
    b = os.path.join(d, "breihen")
    vorher = zeiten(b)
    check("Nachziehen: Ausgangslage -- Ablauf mit Zeitfehler endet mit exit 1", rc == 1, rc)
    check("Nachziehen: Ausgangslage -- B liegt mit Originalzeit in breihen/",
          vorher.get("B00_N1G3_(B+0).jpeg") == "2024:02:14 09:00:05", vorher)
    rc2, o, e = lauf(d, "--zeiten-nachziehen")
    t = zeiten(b)
    check("Nachziehen: exit 0", rc2 == 0, str(rc2) + o + e)
    check("Nachziehen: B auf den geplanten Zeitpunkt gezogen (09:00:32 / :33)",
          t.get("B00_N1G3_(B+0).jpeg") == "2024:02:14 09:00:32"
          and t.get("B00_N3_(B+1)_B02.jpeg") == "2024:02:14 09:00:33", t)
    check("Nachziehen: Dateidatum mitgezogen",
          _mtime_sekunde(os.path.join(b, "B00_N1G3_(B+0).jpeg")) == "2024:02:14 09:00:32",
          _mtime_sekunde(os.path.join(b, "B00_N1G3_(B+0).jpeg")))
    check("Nachziehen: A unveraendert", t.get("A00_N1G3_(B+0).jpeg") == "2024:02:14 09:00:00", t)
    rc3, o3, e3 = lauf(d, "--zeiten-nachziehen")
    check("Nachziehen: zweiter Durchgang findet nichts mehr",
          rc3 == 0 and "0 Datei(en) abweichend" in o3, o3[-300:])


@test
def nachziehen_intakt_schreibt_nichts():
    d = neu("nachziehen_intakt")
    for i, ev in enumerate([0.0, -1.0, 1.0]):
        bild(d, "A%02d.jpeg" % i, "2024:02:14 09:00:0%d" % i, meta=dict(gid=100, ev=ev))
    lauf(d)
    b = os.path.join(d, "breihen")
    vorher = {f: os.stat(os.path.join(b, f)).st_mtime_ns for f in ls(b)}
    rc, o, e = lauf(d, "--zeiten-nachziehen")
    nachher = {f: os.stat(os.path.join(b, f)).st_mtime_ns for f in ls(b)}
    check("Nachziehen auf intaktem Ordner: nichts geschrieben",
          rc == 0 and vorher == nachher and "0 Datei(en) abweichend" in o, o[-300:])


@test
def nachziehen_probelauf():
    d, _ = _zwei_serien_b_scheitert("nachziehen_probe")
    b = os.path.join(d, "breihen")
    vorher = zeiten(b)
    rc, o, e = lauf(d, "--zeiten-nachziehen", "-n")
    check("Nachziehen -n: meldet Abweichung, aendert nichts",
          "abweichend" in o and "Probelauf" in o and zeiten(b) == vorher, o[-300:])


@test
def nachziehen_paare():
    d, _ = _zwei_serien_b_scheitert("nachziehen_paare", ext=".JPG", begleiter=".TIF")
    lauf(d, "--zeiten-nachziehen")
    t = zeiten(os.path.join(d, "breihen"))
    check("Nachziehen: Begleitdateien werden mitkorrigiert",
          t.get("B00_N1G3_(B+0).TIF") == "2024:02:14 09:00:32"
          and t.get("B00_N2_(B-1)_B01.TIF") == "2024:02:14 09:00:33", t)


@test
def nachziehen_ohne_startaufnahme_im_quellordner():
    d, _ = _zwei_serien_b_scheitert("nachziehen_ohnequelle")
    os.unlink(os.path.join(d, "B00.jpeg"))
    rc, o, e = lauf(d, "--zeiten-nachziehen")
    t = zeiten(os.path.join(d, "breihen"))
    check("Nachziehen ohne Quell-Startaufnahme: Hinweis und Zeit aus breihen/",
          "fehlt im Quellordner" in o and t.get("B00_N1G3_(B+0).jpeg") == "2024:02:14 09:00:32", (o[-300:], t))


# ---------------------------------------------------------------------------
# Tests: Einzelfunktionen
# ---------------------------------------------------------------------------

@test
def json_abgeschnitten():
    d = neu("json")
    for i in range(3):
        bild(d, "J%02d.jpeg" % i, "2024:02:14 09:00:0%d" % i)
    wrapper = os.path.join(ARBEIT, "exiftool_stirbt")
    with open(wrapper, "w") as fh:
        fh.write('#!/bin/sh\nexiftool "$@" | head -c 120\nexit 137\n')
    os.chmod(wrapper, 0o755)
    importlib.reload(breihen)
    e = io.StringIO()
    with contextlib.redirect_stderr(e):
        recs = breihen.read_metadata([os.path.join(d, f) for f in ls(d)], exiftool=wrapper)
    check("exiftool stirbt mittendrin: Verzeichnis ausgelassen, gemeldet, gezaehlt",
          recs == [] and breihen.ANALYSE_FEHLER == 1 and "unvollstaendig" in e.getvalue(),
          (len(recs), breihen.ANALYSE_FEHLER, e.getvalue()))


@test
def log_einzeilig():
    importlib.reload(breihen)
    pfad = os.path.join(ARBEIT, "test.log")
    breihen.log_oeffnen(pfad)
    breihen.log("zeit-fehler gid=1 grund=Warning: x\nError: y\n\n  Error: z")
    breihen.LOG_HANDLE.close()
    breihen.LOG_HANDLE = None
    inhalt = open(pfad, encoding="utf-8").read()
    check("Log: mehrzeiliger Text wird eine Zeile", inhalt.count("\n") == 1
          and "grund=Warning: x | Error: y | Error: z" in inhalt, inhalt)


@test
def tiff_wird_verkleinert():
    if not breihen.schaerfe_verfuegbar():
        check("TIFF verkleinert (uebersprungen: numpy/Pillow fehlen)", True)
        return
    pfad = os.path.join(ARBEIT, "gross.tif")
    subprocess.run(["magick", "-size", "6000x4000", "xc:gray50", "+noise", "Random", pfad], check=True)
    a = breihen._luma(pfad)
    check("TIFF 6000x4000 -> Arbeitsgroesse <= %d" % breihen.SCHAERFE_KANTE,
          max(a.shape) <= breihen.SCHAERFE_KANTE, a.shape)


@test
def ev_formatierung():
    faelle = {0.0: "+0", -1 / 3: "-0.3", 2 / 3: "+0.6", -2.0: "-2", 1.5: "+1.5"}
    ist = {k: breihen.format_ev(k) for k in faelle}
    check("EV-Format (abgeschnitten, ohne .0)", ist == faelle, ist)


# ---------------------------------------------------------------------------

def main():
    global ARBEIT, BASIS
    p = argparse.ArgumentParser(description="Regressionstests fuer breihen.py")
    p.add_argument("-k", default="", metavar="MUSTER", help="nur Tests mit MUSTER im Namen")
    p.add_argument("--behalten", action="store_true", help="Arbeitsverzeichnis nicht loeschen")
    args = p.parse_args()

    fehlt = [w for w in ("magick", "exiftool") if shutil.which(w) is None]
    if fehlt:
        print("Werkzeug fehlt: {} -- sudo apt install imagemagick libimage-exiftool-perl"
              .format(", ".join(fehlt)), file=sys.stderr)
        return 2

    ARBEIT = tempfile.mkdtemp(prefix="breihen-tests-")
    BASIS = os.path.join(ARBEIT, "basis.png")
    subprocess.run(["magick", "-size", "900x600", "plasma:fractal", "-colorspace", "Gray",
                    "-normalize", "-colorspace", "sRGB", BASIS], check=True)
    try:
        for fn in TESTS:
            if args.k.lower() not in fn.__name__.lower():
                continue
            try:
                fn()
            except Exception:
                check(fn.__name__ + " (Testfehler)", False, traceback.format_exc())
    finally:
        if args.behalten:
            print("\nArbeitsverzeichnis: " + ARBEIT)
        else:
            shutil.rmtree(ARBEIT, ignore_errors=True)

    n = sum(ok for _, ok in ERGEBNISSE)
    print("\n{}/{} bestanden".format(n, len(ERGEBNISSE)))
    return 0 if n == len(ERGEBNISSE) else 1


if __name__ == "__main__":
    sys.exit(main())
