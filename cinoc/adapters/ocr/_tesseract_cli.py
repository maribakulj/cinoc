"""Le binaire ``tesseract``, lancé par Cinoc lui-même (couche 5).

**Un appel par page.** ``pytesseract`` lançait l'OCR une fois par sortie
(``image_to_string``, ``image_to_data``, ``image_to_alto_xml``) : la page était
lue deux ou trois fois (``docs/ANALYSE_SUBSTITUTION.md``). Ici le binaire reçoit
**tous** ses moteurs de rendu d'un coup (``-c tessedit_create_txt=1 …``) et
écrit ``page.txt``, ``page.tsv``, ``page.xml`` dans un dossier temporaire du
workspace. La ligne de commande est celle que ``pytesseract`` composait
(``-l``, ``--oem``, ``--psm``, ``--dpi``, même chemin d'image) : texte,
confidences et ALTO identiques à l'octet (vérifié sur les 10 pages du pilote).

**Environnement du seul enfant.** ``OMP_THREAD_LIMIT=1`` est donné au
sous-processus, plus posé dans ``os.environ`` du parent (D-282 n'avait pas
d'autre prise) ; une valeur déjà posée par l'utilisateur garde la main.

**Délai et arrêt.** Le processus est attendu par tranches courtes
(``adapters._process``, partagé avec OCR-D) : à l'annulation (``RunControl``)
ou au dépassement du délai de l'étape, il est arrêté (``terminate``, puis
``kill`` s'il insiste) et **attendu** — pas de zombie, sous Windows comme
ailleurs. Délai → ``DeadlineExceeded`` (motif « arrêtée (délai) ») ; arrêt →
``RunCancelledError``.

**Provenance (D19).** ``tesseract --list-langs`` dit où sont les données de
langue et lesquelles sont installées : les ``*.traineddata`` réellement lus
entrent au manifeste et dans la clé d'unité par leur empreinte, et ``--check``
refuse une langue absente (D13).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from cinoc.adapters._process import wait_or_stop
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.run_control import RunControl

logger = logging.getLogger(__name__)

#: Fils OpenMP d'un processus ``tesseract``. Sans borne, chacun en ouvre autant
#: que de cœurs : à 4 workers sur 4 cœurs, 16 fils en attente active, et le
#: pilote BNL perdait 19 pages sur 20 au délai de 120 s pour des pages de 1,4 à
#: 3,4 s (D-281, D1). Le parallélisme de Cinoc est celui des workers.
_OMP_ENV = "OMP_THREAD_LIMIT"
#: Plafond des sondes (``--version``, ``--list-langs``).
_PROBE_SECONDS = 10.0
#: Fin de ``stderr`` citée dans un message d'échec.
_STDERR_CHARS = 400
#: Fenêtre cachée sous Windows (0 ailleurs : l'attribut n'existe pas).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: Moteurs de rendu : nom → (variable qui l'active, extension écrite).
_RENDERERS: dict[str, tuple[str, str]] = {
    "txt": ("tessedit_create_txt", "txt"),
    "tsv": ("tessedit_create_tsv", "tsv"),
    "alto": ("tessedit_create_alto", "xml"),
}

#: Lanceur de sonde, injectable → sondes testables sans binaire.
BinaryRunner = Callable[..., "subprocess.CompletedProcess[bytes]"]

#: Chemin du binaire par valeur de ``PATH`` : résolu une fois, re-résolu si
#: ``PATH`` change ; un binaire introuvable n'est pas mémorisé (il peut être
#: installé pendant que le serveur tourne).
_RESOLVED: dict[str, str] = {}


def tesseract_binary() -> str | None:
    """Chemin du binaire (``tesseract.exe`` sous Windows, par ``PATHEXT``)."""
    key = os.environ.get("PATH", "")
    found = _RESOLVED.get(key)
    if found is None:
        found = shutil.which("tesseract")
        if found is not None:
            _RESOLVED[key] = found
    return found


def child_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """L'environnement **de l'enfant** : celui du parent, ``OMP_THREAD_LIMIT=1``
    par défaut. Une valeur posée (``ENV`` du Space, réglage de qui lance
    ``--workers 1`` sur une page géante) est un choix ; le défaut n'en est pas un."""
    env = dict(os.environ if environ is None else environ)
    env.setdefault(_OMP_ENV, "1")
    return env


def _text(value: bytes | str | None) -> str:
    """Sortie d'une sonde, décodée en UTF-8 quelle que soit la locale."""
    if value is None:
        return ""
    return value if isinstance(value, str) else value.decode("utf-8", "replace")


def _probe(args: list[str], run: BinaryRunner) -> str | None:
    """``stdout`` + ``stderr`` d'une sonde du binaire ; ``None`` s'il manque."""
    binary = tesseract_binary()
    if binary is None:
        return None
    try:
        completed = run(
            [binary, *args],
            capture_output=True,
            timeout=_PROBE_SECONDS,
            check=False,
            env=child_env(),
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _text(completed.stdout) + "\n" + _text(completed.stderr)


def tesseract_binary_version(*, run: BinaryRunner = subprocess.run) -> str | None:
    """1ʳᵉ ligne non vide de ``tesseract --version`` (``tesseract 5.3.4``).

    Best-effort : binaire absent, délai, sortie illisible → ``None``. La bannière
    sort sur ``stdout`` ou ``stderr`` selon le build : on lit les deux.
    """
    output = _probe(["--version"], run)
    if output is None:
        return None
    return next((line.strip() for line in output.splitlines() if line.strip()), None)


@dataclass(frozen=True)
class Tessdata:
    """Ce que ``tesseract --list-langs`` dit des données de langue."""

    #: Dossier lu par le binaire ; ``None`` si sa bannière ne le donne pas
    #: (Tesseract 4) et que ``TESSDATA_PREFIX`` n'est pas posé.
    directory: str | None
    languages: tuple[str, ...]


_DIRECTORY_RE = re.compile(r'"([^"]+)"')


def parse_list_langs(output: str, environ: Mapping[str, str] | None = None) -> Tessdata:
    """Sortie de ``--list-langs`` → dossier + langues installées. **Pur.**

    Tesseract 5 : ``List of available languages in "/…/tessdata/" (7):`` puis
    une langue par ligne. Tesseract 4 ne cite pas le dossier : on prend
    ``TESSDATA_PREFIX`` s'il est posé, sinon il reste inconnu.
    """
    lines = [line.strip() for line in output.splitlines()]
    directory: str | None = None
    languages: list[str] = []
    started = False
    for line in lines:
        if line.startswith("List of available languages"):
            started = True
            match = _DIRECTORY_RE.search(line)
            if match is not None:
                directory = match.group(1)
            continue
        if started and line:
            languages.append(line)
    if directory is None:
        env = os.environ if environ is None else environ
        directory = env.get("TESSDATA_PREFIX") or None
    if directory is not None:
        directory = str(Path(directory))  # sans séparateur final
    return Tessdata(directory=directory, languages=tuple(languages))


def installed_languages(*, run: BinaryRunner = subprocess.run) -> Tessdata | None:
    """``tesseract --list-langs``, **un** appel ; ``None`` sans binaire."""
    output = _probe(["--list-langs"], run)
    return None if output is None else parse_list_langs(output)


def missing_languages(lang: str, tessdata: Tessdata) -> tuple[str, ...]:
    """Les langues de ``lang`` (``fra+deu``) que ``tessdata`` n'a pas."""
    return tuple(name for name in lang.split("+") if name not in tessdata.languages)


def _file_sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return f"sha256:{digest.hexdigest()}"


def tesseract_provenance(
    lang: str, psms: Iterable[int], *, run: BinaryRunner = subprocess.run
) -> dict[str, str]:
    """Binaire **et** données de langue réellement lues — au manifeste et dans
    la clé d'unité (D19) : changer ``fra.traineddata`` change la sortie, donc
    l'unité.

    ``tesseract:tessdata`` = le dossier ; ``tesseract:<langue>.traineddata`` =
    l'empreinte SHA-256 du fichier (``absent`` s'il manque : l'unité échouera en
    le nommant). ``osd`` est lu en plus aux ``psm`` 0 et 1. Binaire absent →
    ``{}`` (best-effort, comme la version).
    """
    version = tesseract_binary_version(run=run)
    if version is None:
        return {}
    found = {"tesseract": version}
    tessdata = installed_languages(run=run)
    if tessdata is None or tessdata.directory is None:
        logger.warning(
            "[tesseract] dossier tessdata inconnu : données de langue non tracées."
        )
        return found
    found["tesseract:tessdata"] = tessdata.directory
    names = set(lang.split("+"))
    if any(psm in (0, 1) for psm in psms):
        names.add("osd")
    for name in sorted(names):
        digest = _file_sha256(Path(tessdata.directory) / f"{name}.traineddata")
        found[f"tesseract:{name}.traineddata"] = digest or "absent"
    return found


def tesseract_command(
    binary: str,
    image: str,
    outbase: str,
    *,
    lang: str,
    psm: int,
    oem: int,
    dpi: int | None,
    renderers: Iterable[str],
) -> list[str]:
    """La ligne de commande, **en liste** (aucun shell). ``lang`` est validé par
    l'adaptateur ; ``image`` est absolu (``realpath``), donc jamais pris pour une
    option. ``--dpi`` seulement s'il est demandé."""
    command = [binary, image, outbase, "-l", lang, "--oem", str(oem), "--psm", str(psm)]
    if dpi is not None:
        command += ["--dpi", str(dpi)]
    for renderer in renderers:
        command += ["-c", f"{_RENDERERS[renderer][0]}=1"]
    return command


def run_tesseract(
    *,
    image_path: str,
    lang: str,
    psm: int,
    oem: int,
    dpi: int | None,
    renderers: tuple[str, ...],
    workspace: str,
    timeout: float,
    control: RunControl,
    what: str = "tesseract",
) -> dict[str, bytes]:
    """**Un** appel du binaire ; rend les octets de chaque sortie **produite**
    (``{"txt": …, "tsv": …, "alto": …}``) — à l'appelant de dire laquelle est
    exigée. Binaire absent, code de sortie non nul → ``AdapterStepError``."""
    binary = tesseract_binary()
    if binary is None:
        raise AdapterStepError(
            f"{what} : binaire « tesseract » introuvable dans le PATH "
            "(installer Tesseract 5 et ses données de langue)."
        )
    # Le chemin que pytesseract passait (identité à l'octet, D-300). L'ALTO le
    # recopie dans ``fileName`` : l'adaptateur n'en publie que le nom (D-301).
    source = os.path.realpath(os.path.normpath(os.path.normcase(image_path)))
    with tempfile.TemporaryDirectory(
        prefix=".tesseract-", dir=workspace, ignore_cleanup_errors=True
    ) as tmp:
        outbase = os.path.join(tmp, "page")
        command = tesseract_command(
            binary, source, outbase, lang=lang, psm=psm, oem=oem, dpi=dpi,
            renderers=renderers,
        )
        stderr_path = Path(tmp) / "stderr.log"
        with stderr_path.open("wb") as stderr:
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr,
                    env=child_env(),
                    creationflags=_NO_WINDOW,
                )
            except OSError as exc:
                raise AdapterStepError(
                    f"{what} : binaire « tesseract » non exécutable "
                    f"({exc.strerror or exc})."
                ) from exc
            code = wait_or_stop(
                process, timeout=timeout, control=control, what=what,
                subject=image_path,
            )
        if code != 0:
            message = " ".join(_text(stderr_path.read_bytes()).split())
            raise AdapterStepError(
                f"{what} a échoué sur {image_path!r} : code {code} : "
                f"{message[-_STDERR_CHARS:] or '(aucun message)'}"
            )
        produced: dict[str, bytes] = {}
        for renderer in renderers:
            path = Path(f"{outbase}.{_RENDERERS[renderer][1]}")
            if path.is_file():
                produced[renderer] = path.read_bytes()
        return produced


__all__ = [
    "Tessdata",
    "child_env",
    "installed_languages",
    "missing_languages",
    "parse_list_langs",
    "run_tesseract",
    "tesseract_binary",
    "tesseract_binary_version",
    "tesseract_command",
    "tesseract_provenance",
]
