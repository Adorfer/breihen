# breihen

Skript zur Vorverarbeitung von automatischen Belichtungsreihen
(Auto Exposure Bracketing, AEB) aus Nikon-Kameras für die Weiterverarbeitung
in HDR-Software, z. B. **Photomatix**.

## Ziel

Photomatix (und ähnliche Software) erkennt zusammengehörige Belichtungsreihen
anhand der EXIF-Metadaten — vor allem über den zeitlichen Abstand der
Aufnahmen. Das scheitert in der Praxis an rasch hintereinander ausgelösten
Reihen, unvollständigen Reihen und Einzelbildern dazwischen. `breihen.py`
bereitet das Material so auf, dass die automatische Erkennung sicher greift:

- **Sichere Reihen-Erkennung**: Serien werden über die Nikon-`BurstGroupID`
  aus den MakerNotes gruppiert — nicht über Zeitheuristik. Die Bilder einer
  Reihe erhalten dann einheitliche Zeitstempel (Startbild T, Folgebilder
  T + 1 s), aufeinanderfolgende Reihen einen erzwungenen Mindestabstand von
  32 s (bei Langzeitbelichtungen > 14 s entsprechend mehr). Damit trennt die
  Zeitabstands-Erkennung der HDR-Software zuverlässig.
- **Datei-Management**: Alle Bilder einer Reihe werden in das Unterverzeichnis
  `./breihen` verschoben (das Startbild als Kopie — es bleibt zusätzlich
  unverändert im Ausgangsverzeichnis liegen) und dabei so umbenannt, dass
  Reihe, Position und Belichtungskorrektur direkt ablesbar sind.

## Namensschema

| Datei | Beispiel |
|---|---|
| Startbild einer 7er-Reihe, Korrektur ±0 | `P2140944_N1G7_(B+0).jpeg` |
| 4. Bild derselben Reihe, Korrektur −2 EV | `P2140944_N4_(B-2)_P2140947.jpeg` |
| RAW+JPEG: Begleitdatei zur selben Aufnahme | `P2140944_N4_(B-2)_P2140947.NEF` |
| Blitz- / Weißabgleich- / ADL-Reihe | `(F+1)` / `(W+3-2)` / `(A_High)` |
| Serienbild nach Schärferang (Typ „keine“) | `P2140944_N1G5_(S1_842).jpeg` |

## Aufruf

```bash
python3 breihen.py /pfad/zum/bildordner --dry-run     # erst ansehen
python3 breihen.py /pfad/zum/bildordner               # ausführen
python3 breihen.py /pfad --rekursiv                   # samt Unterordnern
python3 breihen.py --help                             # alle Optionen + Doku
```

Standardmäßig werden nur echte Belichtungsreihen (AE) bearbeitet;
`--allbracketing` bzw. `--typen ae,flash,wb,adl,keine` nimmt weitere
Reihenarten dazu. Bei Serien ohne Belichtungsvariation kann das Skript das
schärfste Bild bestimmen und im Ausgangsverzeichnis belassen
(`--schaerfe-bericht` zeigt vorab nur die Messwerte). Vor der ersten
Schreibaktion werden Dateirechte und Speicherplatz geprüft; jeder Lauf
protokolliert nach `breihen.log` (grep-freundlich, mit Prozess-ID).

## Hinweise für den Einsatz

- **Belichtungsreihen im Serienbild-Modus (CL/CH) aufnehmen.** Nur dort vergibt
  die Kamera eine `BurstGroupID`; im Einzelbild-Modus ist sie 0, und die
  Reihe wird nicht erkannt.
- **RAW+JPEG** wird unterstützt: Dateien derselben Aufnahme (gleicher Name,
  andere Endung) laufen als Paar — gleicher neuer Name, gleiche Aktion,
  gleiche Zeit.
- **Eine Kamera je Ordner.** Gruppiert wird zwar nach Seriennummer und ID,
  zwei Bodies vermischen sich also nicht; vorgesehen ist der Einsatz aber
  pro Kamera.
- **Die `BurstGroupID` läuft alle 2048 Aufnahmen um.** Sie ist
  `(Bildnummer × 32) mod 65536`, nachgemessen an einer Z5II: bei ~6400
  Aufnahmen einer Reise dreimal umgelaufen, dieselbe ID an zwei Tagen
  vergeben. Solche Kollisionen trennt das Skript an der Zeitlücke
  (`--max-gap`, per Vorgabe 2 × Belichtungszeit + 30 s — innerhalb echter
  Serien lagen höchstens 1 s zwischen zwei Bildern).
- **Ein zweiter Lauf ist unschädlich.** Bereits abgelegte Serien werden
  übersprungen; eine nur teilweise abgelegte Serie (früherer Lauf
  abgebrochen) wird als *unvollständig* gemeldet und nicht angefasst.

## Installation (Ubuntu 26.04)

```bash
sudo apt install libimage-exiftool-perl python3-scipy python3-pil libraw-bin
```

Nur Pflicht ist `libimage-exiftool-perl` (plus Python 3.7+); die übrigen
Pakete braucht allein die optionale Schärfemessung. Details im Docstring
des Skripts (`python3 breihen.py --help`).

## Tipp: Photomatix-Einstellungen für Batch-Belichtungsreihen

In Photomatix unter *Belichtungsreihen-Auswahl → Erweitert*
(Dialog „Erweiterte Auswahl – Optionen“):

- **Automatische Erkennung der Belichtungsreihen**: Reihen bestehen aus
  **2 bis 11** Bildern
- ☑ **Reihen können eine gerade Anzahl Bilder haben**
- **Maximale Zeit zwischen zwei Belichtungen: 14 Sekunden**

Das passt exakt zu den von `breihen.py` gesetzten Zeitstempeln: Innerhalb
einer Reihe liegt 1 Sekunde zwischen den Bildern (weit unter 14 s),
zwischen zwei Reihen mindestens 32 Sekunden (sicher darüber) — die
automatische Erkennung kann so nicht mehr verschmelzen oder falsch trennen.

Die Erkennung von Photomatix basiert auf den EXIF-Metadaten, nicht auf dem
Bildinhalt. Sie funktioniert daher nur, wenn die EXIF-Daten nicht entfernt
wurden.

## Lizenz

[BSD-3-Clause](LICENSE)
