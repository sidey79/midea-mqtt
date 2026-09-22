# Release-Prozess: Plan bis Version 1.0

Status: entschieden, Umsetzung ausstehend

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

Stand nach dem Merge von PR #25 (Trivy-Scan) und PR #26 (distroless-Runtime),
`VERSION` steht auf `0.3.0`.

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
4. **Digest-Updates ändern das Image, ohne die Version zu ändern.**
   `renovate.json` nutzt `docker:pinDigests` zusammen mit
   `default:automergeDigest`. Aktualisierungen des Basisimages laufen damit ohne
   menschliche Freigabe nach `main` und erzeugen dort ein neues `sha-`-Image,
   während `VERSION` unverändert bleibt. Der Automerge selbst ist erwünscht (siehe
   Entscheidung 1); was fehlt, ist der begleitende Versions-Bump.

Für die Umsetzung relevant: Renovate läuft in diesem Repository nicht als
gehostete Mend-App, sondern als eigene Instanz (`sidey79-self-hosted-renovate`).
Damit steht `postUpgradeTasks` zur Verfügung, das in der gehosteten Variante
gesperrt ist.

## Zielbild des Ablaufs

> **Update (siehe „Jeder Merge veröffentlicht" unter Getroffene Entscheidungen):**
> Der ursprüngliche Ablauf sah einen eigenen, bewusst geschnittenen Release-PR
> vor (Schritte 4–5 unten). Das ist abgelöst: Ein Merge nach `main`, der eine
> Datei berührt, die im Image landet (`Dockerfile`, `requirements.txt`,
> `midea_mqtt_bridge.py`), und dessen `VERSION` dabei unverändert bleibt, löst
> die Pipeline selbst aus — sie hebt die Patch-Stelle an, überführt
> `Unreleased` in einen datierten Abschnitt und veröffentlicht direkt. Ein
> eigener Release-PR ist nur noch nötig, wenn eine Änderung mehr als einen
> Patch-Bump verdient (siehe Schritt 4 in „Umsetzungsschritte" Punkt 4a).

Für jede Änderung:

1. Feature-Branch von `main`, Änderung, Pull Request.
2. Der PR pflegt seinen Eintrag unter `## [Unreleased]` in `CHANGELOG.md` gleich
   mit. Der Changelog entsteht damit fortlaufend und muss beim Release nicht
   nachträglich aus Commits rekonstruiert werden.
3. Merge nach `main`. Berührt die Änderung keine Datei, die im Image landet,
   entsteht **kein** veröffentlichtes Image — die Pipeline baut, testet und
   scannt weiterhin, pusht aber nichts.

Für ein Release:

4. **Regelfall (Patch):** Berührt die Änderung eine Datei, die im Image landet,
   und bleibt `VERSION` im selben Merge unverändert, hebt die Pipeline die
   Patch-Stelle selbst an und überführt `Unreleased` in einen datierten
   Abschnitt — ohne eigenen Release-PR.
   **Minor/Major:** Verdient eine Änderung mehr als einen Patch-Bump, setzt der
   Autor `VERSION` im selben PR bewusst höher; die Pipeline erkennt die eigene
   Wahl und bumpt nicht zusätzlich.
5. Der Merge nach `main` löst in beiden Fällen dieselbe Veröffentlichung aus:
   SemVer-Tags nach GHCR, Git-Tag `vMAJOR.MINOR.PATCH`, GitHub Release mit dem
   Changelog-Abschnitt als Release-Notes.

Der Auslöser bleibt damit die `VERSION`-Änderung auf `main` — ob sie ein Mensch
im PR oder die Pipeline selbst danach setzt, macht für den Rest der Pipeline
keinen Unterschied. Das braucht keine Sonderrechte für das Setzen von Tags von
Hand. Die Alternative — Push eines Git-Tags als Auslöser — würde einen zweiten,
an der PR-Review vorbeilaufenden Weg in die Registry öffnen und wird deshalb
nicht verfolgt.

## Umsetzungsschritte

Jeder Schritt ist ein eigener Branch und PR.

### 1. Changelog einführen

- `CHANGELOG.md` nach dem Format von [Keep a Changelog](https://keepachangelog.com/de/1.1.0/)
  anlegen, mit `## [Unreleased]` an der Spitze.
- Die bisherigen Versionen — `0.1.0`, `0.1.1`, `0.1.2`, `0.2.0` und `0.3.0` —
  rückwirkend aus der Commit-Historie eintragen.
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
- `latest` bleibt erhalten, wird aber ausdrücklich nicht als stabiler Kanal
  verstanden, sondern als unspezifischer Verweis auf das jeweils neueste Release.
  Das gehört so in die README, damit niemand `latest` für eine Stabilitätszusage
  hält; für den Produktivbetrieb ist auf `x.y.z` zu pinnen. Am Verhalten der
  Pipeline ändert sich nichts: Pre-Releases erhalten weiterhin kein `latest`,
  weil der Tag sonst unangekündigt Vorabversionen ausliefern würde.

### 3. Git-Tag und GitHub Release erzeugen

- Im selben Job, nach erfolgreichem Push, ein annotiertes Git-Tag
  `v${VERSION}` setzen und pushen.
- GitHub Release aus dem passenden Changelog-Abschnitt erstellen, als
  Pre-Release markiert, wenn `VERSION` ein Suffix trägt.
- Dafür ist `contents: write` nötig; die Berechtigung ist eng zu halten, idealer-
  weise durch Auslagerung in einen eigenen Job mit eigenen `permissions`.

### 4. Jeder image-relevante Merge wird zum Patch-Release

Der Automerge bleibt bestehen. Die Versionsentscheidung liegt aber an einer
einzigen Stelle: dem Schritt „Auto-cut a patch release for image-relevant
merges" in `.github/workflows/docker-image.yml`, der bei jedem Push auf `main`
läuft. Das gilt gleichermaßen für Renovate-PRs wie für von Hand geschriebene
Feature- und Fix-PRs — eine Aktualisierung, die in Schritt 4a (Zielbild)
beschriebene menschliche Minor/Major-Entscheidung ausgenommen.

Maßgeblich ist, ob eine Änderung im ausgelieferten Image landet, nicht um
welche Art von Änderung es sich handelt. Erfasst werden deshalb `Dockerfile`,
`requirements.txt` und `midea_mqtt_bridge.py`. Aktualisierungen von
GitHub-Actions-Versionen, an Doku oder am Beispiel in `docker-compose.yml`
verändern das Image nicht und lösen folglich auch kein Release aus.

- `scripts/cut-release.sh` erhöht die Patch-Stelle in `VERSION` und überführt
  den bestehenden `Unreleased`-Abschnitt in einen datierten Versionsabschnitt.
  Es setzt voraus, dass `Unreleased` bereits Einträge enthält — leer zu sein
  ist ein Fehler, kein Grund zum Nichtstun: Eine image-relevante Änderung ohne
  Changelog-Eintrag ist ein Policy-Verstoß und lässt den Workflow-Lauf
  fehlschlagen, statt ihn stillschweigend zu überspringen.
- Der Workflow-Schritt bumpt nur, wenn `VERSION` im selben Merge unverändert
  geblieben ist. Hat der PR selbst schon eine höhere Version gesetzt — etwa für
  einen bewussten Minor- oder Major-Bump —, erkennt der Schritt das an einem
  Diff auf `VERSION` zwischen dem vorherigen und dem neuen `main`-Stand und
  lässt die Wahl unangetastet.
- Der Bump-Commit (`chore: release x.y.z`) entsteht und wird direkt im selben
  Job auf `main` gepusht, bevor Build, Tag und Release im selben Lauf
  weiterlaufen. Ein zweiter, durch den Push ausgelöster Workflow-Lauf wird
  bewusst nicht benötigt — ein Commit, den ein Workflow mit `GITHUB_TOKEN`
  erzeugt, löst ohnehin keine weiteren Läufe aus. Der `release`-Job checkt
  deshalb explizit den vom `docker-image`-Job gemeldeten `release_sha` aus statt
  `github.sha`, damit Tag und Release auf dem gebumpten Commit landen.
- `scripts/renovate-changelog-entry.sh` (vormals `renovate-patch-release.sh`)
  schreibt für Renovate-PRs nur noch den Changelog-Eintrag unter `Unreleased`
  — das Bumpen selbst übernimmt jetzt einheitlich der Workflow-Schritt oben,
  egal ob die Änderung von Renovate oder von einem Menschen stammt.
- Die Einträge stehen in einem eigenen Abschnitt `### Dependencies` an der
  Spitze von `Unreleased`, nicht in den bestehenden Kategorien. Ein Bot-Eintrag
  soll sich nicht unter die handgeschriebenen Notizen eines anstehenden Releases
  mischen: Beim Schneiden des Releases bleibt so auf einen Blick erkennbar, was
  von Renovate kam.
- Welches Paket sich bewegt hat, liefert Renovate selbst. `renovate.json` füllt
  über `postUpgradeTasks.dataFileTemplate` eine Datei mit einem
  Tab-getrennten Satz je Upgrade (`depName`, `currentValue`, `newValue`,
  `currentDigestShort`, `newDigestShort`); ihren Pfad findet das Skript in der
  Umgebungsvariablen `RENOVATE_POST_UPGRADE_COMMAND_DATA_FILE`. Daraus entsteht
  etwa `- Update msmart-ng from 2026.8.0 to 2026.9.0.` beziehungsweise, wenn
  sich nur der Digest bewegt hat, `- Update the python image to digest
  sha256:…`. Formuliert wird im Skript und nicht in der Handlebars-Vorlage,
  damit sich der Text ohne Renovate testen lässt. Fehlt die Datei — etwa bei
  einem Lauf von Hand —, fällt das Skript auf die frühere Sammelformulierung
  anhand der geänderten Dateien zurück.
- `renovate.json` ruft das Skript über eine `packageRule` mit
  `matchFileNames: ["Dockerfile", "requirements.txt"]` auf, mit
  `executionMode: "branch"`, damit mehrere Updates in einem Branch nur einen
  Eintrag erzeugen.
- Voraussetzung: Das Skript muss in der Konfiguration der Renovate-Instanz unter
  `allowedCommands` freigegeben sein. Das ist Instanz-Konfiguration und liegt
  nicht in diesem Repository.
- `fileFilters` auf `VERSION` und `CHANGELOG.md` begrenzen, damit die Aufgabe
  keine anderen Dateien in den PR zieht.

Ein Fallstrick, der bei der Umsetzung zu prüfen war:

- `postUpgradeTasks` wirken nicht rückwirkend auf bereits offene Renovate-Pull-
  Requests. Nach einer Änderung an dieser Konfiguration müssen bestehende
  Branches neu erzeugt werden, etwa über die Rebase-Checkbox im Pull Request.

### 5. Trivy als Release-Gate

- Der Scan bleibt für Merges nach `main` reines Reporting.
- Zusätzlich bricht ein Release ab, wenn ein CRITICAL-Fund vorliegt. Umsetzung:
  ein zweiter Trivy-Aufruf mit `severity: CRITICAL` und `exit-code: '1'`, der nur
  läuft, wenn `publish_version_tags` wahr ist.
- Der Abbruch muss vor dem Push in die Registry greifen, damit kein Image
  veröffentlicht wird, das anschließend als fehlerhaft markiert werden müsste.

### 6. Container-Smoke-Test

Die bestehende Pipeline-Spezifikation hat den Smoke-Test zurückgestellt, bis das
Image einen testbaren Aufruf anbietet. Der fehlende Baustein dafür ist ein
`--version`-Flag.

- `midea_mqtt_bridge.py` erhält in der bereits vorhandenen `parse_args`-Funktion
  ein `--version`. Da `parse_args` in `main` vor der Konstruktion von
  `MideaBridge` läuft, greift das Flag vor der Prüfung der Pflicht-Umgebungs-
  variablen und beendet das Programm ohne Laufzeitkonfiguration.
- Die Versionsangabe kommt aus der Datei `VERSION`, die dafür ins Image kopiert
  und relativ zum Skript gelesen wird. Damit bleibt `VERSION` die einzige
  Quelle, und es braucht kein Build-Argument. Fällt das Lesen aus, wird
  `unknown` ausgegeben statt eine Ausnahme zu werfen — ein Diagnose-Flag darf
  den Start nicht gefährden.
- Der Test in der Pipeline nutzt das Image, das für den Trivy-Scan ohnehin schon
  lokal geladen wird, und braucht deshalb keinen zusätzlichen Build:

  ```bash
  test "$(docker run --rm "$IMAGE:scan" --version)" = "$(cat VERSION)"
  ```

- Damit prüft der Smoke-Test zwei Dinge auf einmal: dass der Container
  überhaupt startet und seinen Interpreter samt Abhängigkeiten findet, und dass
  das gebaute Image die Version trägt, unter der es veröffentlicht werden soll.
- Der Test läuft nur auf `linux/amd64`, weil nur diese Architektur auf dem
  Runner ohne Emulation ausführbar ist. Für die anderen Architekturen bleibt es
  beim Build als Nachweis.

### 7. Weg zu 1.0.0

`1.0.0` ist erreicht, wenn die folgenden Kriterien erfüllt sind:

- Der MQTT-Topic-Aufbau und das State-Payload-Format gelten als stabil, weil
  Nutzer ihre FHEM- oder Home-Assistant-Konfiguration daran binden. Ein
  Breaking Change daran wäre ab 1.0 ein Major-Release.
- Die unterstützten Umgebungsvariablen sind dokumentiert und benannt stabil.
- Die Discovery-Funktion ist aus dem Erprobungsstand heraus.
- Der Release-Prozess aus diesem Dokument ist umgesetzt, damit 1.0 nicht die
  erste Version ist, die ihn erprobt.

## Getroffene Entscheidungen

1. **Sicherheitsupdates lösen automatisch ein Patch-Release aus.** Ein
   Digest-Update des Basisimages hebt im selben Renovate-PR die Patch-Version an
   und bringt seinen Changelog-Eintrag mit; der Automerge veröffentlicht damit
   regulär ein Release. Bewusst in Kauf genommen wird, dass diese Releases ohne
   menschliche Entscheidung entstehen — der Gegenwert ist, dass Sicherheitsfixes
   Nutzer ohne Verzögerung erreichen. Umsetzung siehe Schritt 4.
2. **`latest` bleibt, gilt aber als unspezifisch.** Der Tag wird nicht als
   stabiler Kanal verstanden, sondern verweist schlicht auf das neueste Release.
   Das ist eine Dokumentationsaufgabe in der README, keine Änderung an der
   Pipeline. Umsetzung siehe Schritt 2.
3. **Trivy blockiert Releases, nicht Merges.** Merges nach `main` bleiben
   ungehindert; ein Release mit CRITICAL-Fund bricht ab. Umsetzung siehe
   Schritt 5.
4. **Der Changelog wird vollständig rekonstruiert**, also `0.1.0`, `0.1.1`,
   `0.1.2`, `0.2.0` und `0.3.0` rückwirkend eingetragen. Umsetzung siehe
   Schritt 1.
5. **Der Smoke-Test ist Teil des Umfangs**, nicht optional. Er setzt ein
   `--version`-Flag voraus, das zugleich der Diagnose im Betrieb dient.
   Umsetzung siehe Schritt 6.
6. **Die Kriterien für 1.0.0 gelten als bestätigt.** Siehe Schritt 7.
7. **Jeder Merge veröffentlicht.** Der ursprünglich vorgesehene, bewusst
   geschnittene Release-PR entfällt für den Regelfall. Berührt ein Merge nach
   `main` eine Datei, die im Image landet, und lässt `VERSION` dabei
   unverändert, hebt die Pipeline selbst die Patch-Stelle an und
   veröffentlicht — ohne weiteren Zwischenschritt. Vorbild ist der
   `alexa-cookie`-Release-Workflow, bei dem ebenfalls kein separater
   Release-PR nötig ist. Ausdrücklich erhalten bleibt die Unterscheidung nach
   dem, was im Image landet: Änderungen an CI, Doku oder Tests bleiben
   versionslos, wie bisher. Eine Änderung, die mehr als einen Patch-Bump
   verdient, bekommt ihre Minor- oder Major-Version weiterhin bewusst von
   einem Menschen, indem `VERSION` im selben PR gesetzt wird — die Pipeline
   bumpt dann nicht zusätzlich. Umsetzung siehe Schritt 4.

Damit ist der Plan vollständig entschieden; offene Punkte bestehen keine mehr.
