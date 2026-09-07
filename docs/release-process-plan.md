# Release-Prozess: Plan bis Version 1.0

Status: Arbeitsentwurf, noch nicht umgesetzt

## Ziel

Das Projekt soll eine nachvollziehbare Release-Planung erhalten und auf Version
`1.0.0` hinarbeiten. Leitregel für den Zielzustand:

> Änderungen erreichen Nutzer ausschließlich über ein Release. Jedes Release hat
> einen Changelog-Eintrag, und jedes veröffentlichte Container-Image gehört zu
> genau einem Release.

Damit wird abgelöst, dass jeder Merge nach `main` unmittelbar ein konsumierbares
Image erzeugt.

Dieses Dokument setzt den Abschnitt „GitHub Releases" aus
`temporary-image-pipeline-spec.md` fort, der Releases bewusst aus der ersten
Pipeline herausgehalten und für später vorgesehen hat.

## Ist-Zustand

Stand nach dem Merge von PR #25 (Trivy-Scan). PR #26 (distroless-Runtime,
`VERSION` 0.3.0) ist zu diesem Zeitpunkt offen.

Was bereits zum Ziel passt:

1. Die Version wird explizit in der Datei `VERSION` gepflegt und im Workflow
   gegen ein SemVer-Pattern validiert.
2. Versions-Tags (`x.y.z`, `x.y`, `x`, `latest`) entstehen nur, wenn sich
   `VERSION` in einem Push auf `main` tatsächlich geändert hat. Der Schritt
   „Determine whether to publish version tags" vergleicht dafür `VERSION`
   zwischen `github.event.before` und `github.sha`.
3. Pre-Releases (`1.3.0-rc.1`) erhalten weder `latest` noch Major- oder
   Minor-Tags.
4. Commits folgen laut `agents.md` einer semantischen Konvention, und alle
   Änderungen laufen über Feature-Branches. Das ist eine brauchbare Grundlage
   für Changelog-Einträge.

Was dem Ziel entgegensteht:

1. **`sha-`-Tags bei jedem Merge.** Die Metadata-Action erzeugt
   `type=sha,prefix=sha-` unabhängig davon, ob sich `VERSION` geändert hat. Bei
   jedem Push auf `main` landet also ein neues, ziehbares Image in GHCR. Das ist
   der zentrale Widerspruch zur Leitregel.
2. **Kein Changelog.** Es gibt keine `CHANGELOG.md`; was in einer Version
   steckt, lässt sich nur aus der Commit-Historie rekonstruieren.
3. **Kein Git-Tag, kein GitHub Release.** Veröffentlichte Versionen sind derzeit
   nur GHCR-Tags. Im Repository markiert nichts den Stand, aus dem eine Version
   gebaut wurde, und es gibt keine Release-Notes.
4. **Renovate merged Digest-Updates automatisch.** `renovate.json` nutzt
   `docker:pinDigests` zusammen mit `default:automergeDigest`. Aktualisierungen
   des Basisimages laufen damit ohne menschliche Freigabe nach `main` — und
   erzeugen dort heute unmittelbar ein neues `sha-`-Image, ohne dass `VERSION`
   sich ändert.

## Zielbild des Ablaufs

Für jede Änderung:

1. Feature-Branch von `main`, Änderung, Pull Request.
2. Der PR pflegt seinen Eintrag unter `## [Unreleased]` in `CHANGELOG.md` gleich
   mit. Der Changelog entsteht damit fortlaufend und muss beim Release nicht
   nachträglich aus Commits rekonstruiert werden.
3. Merge nach `main`. Es entsteht **kein** veröffentlichtes Image. Die Pipeline
   baut, testet und scannt weiterhin, pusht aber nichts.

Für ein Release:

4. Ein Release-PR bündelt zwei Dinge: den Bump in `VERSION` und das Überführen
   des `Unreleased`-Abschnitts in einen Versionsabschnitt mit Datum.
5. Der Merge dieses PRs nach `main` löst die Veröffentlichung aus: SemVer-Tags
   nach GHCR, Git-Tag `vMAJOR.MINOR.PATCH`, GitHub Release mit dem
   Changelog-Abschnitt als Release-Notes.

Der Auslöser bleibt damit die `VERSION`-Änderung auf `main`. Das ist bereits
implementiert und erprobt, bleibt über einen PR reviewbar und braucht keine
Sonderrechte für das Setzen von Tags von Hand. Die Alternative — Push eines
Git-Tags als Auslöser — würde einen zweiten, an der PR-Review vorbeilaufenden
Weg in die Registry öffnen und wird deshalb nicht verfolgt.

## Umsetzungsschritte

Jeder Schritt ist ein eigener Branch und PR.

### 1. Changelog einführen

- `CHANGELOG.md` nach dem Format von [Keep a Changelog](https://keepachangelog.com/de/1.1.0/)
  anlegen, mit `## [Unreleased]` an der Spitze.
- Die bisherigen Versionen — `0.1.0`, `0.1.1`, `0.1.2` und `0.2.0` — rückwirkend
  aus der Commit-Historie eintragen, soweit sinnvoll rekonstruierbar.
- `agents.md` um die Regel ergänzen, dass jeder nutzersichtbare Change seinen
  Changelog-Eintrag im selben PR mitbringt.

### 2. Veröffentlichung an das Release binden

- `type=sha,prefix=sha-` aus der Metadata-Action entfernen.
- Damit pusht die Pipeline nur noch, wenn `publish_version_tags` wahr ist. Der
  bestehende `push:`-Ausdruck in `Build Docker image` ist entsprechend zu
  erweitern, sonst läuft ein Push auf `main` ohne `VERSION`-Änderung in einen
  Build-and-Push ohne Tags.
- Für die Rückverfolgbarkeit eines Images auf einen Commit sind
  OCI-Labels der bessere Weg als ein eigener Tag: `docker/metadata-action`
  setzt `org.opencontainers.image.revision` bereits automatisch.

### 3. Git-Tag und GitHub Release erzeugen

- Im selben Job, nach erfolgreichem Push, ein annotiertes Git-Tag
  `v${VERSION}` setzen und pushen.
- GitHub Release aus dem passenden Changelog-Abschnitt erstellen, als
  Pre-Release markiert, wenn `VERSION` ein Suffix trägt.
- Dafür ist `contents: write` nötig; die Berechtigung ist eng zu halten, idealer-
  weise durch Auslagerung in einen eigenen Job mit eigenen `permissions`.

### 4. Renovate an den Release-Prozess anpassen

- `default:automergeDigest` entfernen, damit Digest-Updates des Basisimages
  sichtbar über einen PR laufen.
- Digest-Updates sammeln sich dann in `Unreleased` und gehen mit dem nächsten
  Patch-Release raus.

### 5. Weg zu 1.0.0

Zu klären ist, was `1.0.0` inhaltlich bedeutet. Vorschlag als Kriterien:

- Der MQTT-Topic-Aufbau und das State-Payload-Format gelten als stabil, weil
  Nutzer ihre FHEM- oder Home-Assistant-Konfiguration daran binden. Ein
  Breaking Change daran wäre ab 1.0 ein Major-Release.
- Die unterstützten Umgebungsvariablen sind dokumentiert und benannt stabil.
- Die Discovery-Funktion ist aus dem Erprobungsstand heraus.
- Der Release-Prozess aus diesem Dokument ist umgesetzt, damit 1.0 nicht die
  erste Version ist, die ihn erprobt.

## Offene Entscheidungen

1. **Sicherheitsupdates ohne Feature-Änderung.** Wenn ein Digest-Update des
   Basisimages eine Schwachstelle schließt, erreicht es Nutzer im Zielbild erst
   mit dem nächsten Release. Entweder wird dafür bewusst ein Patch-Release
   gefahren, oder es braucht eine Ausnahme. Ein automatisiertes Patch-Release
   bei Digest-Updates wäre möglich, steht aber in Spannung zur Leitregel, dass
   jedes Release einen bewussten Changelog-Eintrag hat.
2. **Umgang mit `latest`.** Bleibt es beim aktuellen Verhalten, dass `latest`
   auf die neueste stabile Version zeigt, oder soll es zugunsten expliziter
   Versions-Pins entfallen?
3. **Trivy als Merge-Gate.** Der Scan ist derzeit bewusst reines Reporting. Für
   1.0 wäre zu entscheiden, ob CRITICAL-Funde einen Release blockieren sollen.
4. **Rückwirkender Changelog.** Wie weit zurück lohnt sich die Rekonstruktion —
   nur `0.2.0`, oder alle bisherigen Versionen?
5. **Container-Smoke-Test.** Die bestehende Pipeline-Spezifikation hat ihn
   zurückgestellt, bis das Image eine testbare Option anbietet. Vor 1.0 wäre ein
   `--version`-Flag ein kleiner Schritt mit doppeltem Nutzen: Smoke-Test in der
   Pipeline und Diagnose im Betrieb.
