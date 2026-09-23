"""Le manifeste dit **où** les sorties d'un run ont été conservées.

Le workspace d'un run est un dossier temporaire, effacé à la sortie. Sans cette
trace, un ``RunResult`` ne peut pas retrouver ce qu'il a lui-même produit : ni
relire ce qu'un moteur a écrit sur une page, ni recalculer une analyse après
coup.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from cinoc.app.resume import ResumeStore


def test_le_store_expose_son_dossier(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "reprise")
    assert store.base_dir == tmp_path / "reprise"
    assert store.base_dir.is_dir()


def test_le_store_copie_les_fichiers_hors_du_workspace(tmp_path: Path) -> None:
    """La propriété qui rend tout le reste possible, et qui n'était nommée nulle
    part : ``save`` **copie**, il ne référence pas.

    Un run dont le workspace a disparu garde donc ses sorties.
    """
    from cinoc.domain.artifacts import Artifact, ArtifactType
    from cinoc.domain.usage import ResourceUsage

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sortie = workspace / "page.txt"
    sortie.write_text("le texte produit", encoding="utf-8")
    store = ResumeStore(tmp_path / "reprise")
    store.save(
        "cle",
        {
            ArtifactType.RAW_TEXT: Artifact(
                id="d:p:raw_text",
                document_id="d",
                type=ArtifactType.RAW_TEXT,
                uri=str(sortie),
            )
        },
        ResourceUsage(),
    )
    # Le workspace disparaît, comme à la fin d'un vrai run.
    shutil.rmtree(workspace)

    charge = store.load("cle")
    assert charge is not None
    artefacts, _ = charge
    conserve = artefacts[ArtifactType.RAW_TEXT]
    assert conserve.uri is not None
    assert Path(conserve.uri).read_text(encoding="utf-8") == "le texte produit"


def test_le_manifeste_porte_le_dossier(tmp_path: Path) -> None:
    from cinoc.domain.run import RunManifest

    manifeste = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        code_version="1.0",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        artifacts_dir=str(tmp_path),
    )
    assert manifeste.artifacts_dir == str(tmp_path)


def test_sans_conservation_le_champ_est_vide() -> None:
    """``None`` dit la vérité : un run sans cache n'a rien gardé."""
    from cinoc.domain.run import RunManifest

    horodatage = datetime(2026, 1, 1, tzinfo=UTC)
    manifeste = RunManifest(
        run_id="r", corpus_name="c", n_documents=1, code_version="1.0",
        started_at=horodatage, completed_at=horodatage,
    )
    assert manifeste.artifacts_dir is None
