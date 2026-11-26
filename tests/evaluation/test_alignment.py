"""Un seul alignement optimal pour les analyses au mot et au caractère (D-286).

Les cinq analyses qui alignaient par ``difflib.SequenceMatcher`` — taxonomie,
hallucinations, confusions de caractères, mots manqués, modernisation lexicale —
ne voyaient pas les mêmes erreurs que le WER et le CER affichés à côté :
``difflib`` cherche le plus long bloc commun d'abord, ce qui n'est pas un
alignement de coût minimal. Sur un article bégayé (« le roi le le roi le
roi »), il comptait deux lacunes et trois insertions là où le WER voit **une**
insertion.

Référence indépendante : ``jiwer.process_words`` (dépendance *dev*), au mot sur
``str.split`` — la découpe du WER de Cinoc. Chaque cas ci-dessous a d'abord été
vu **rouge** sur l'alignement ``difflib`` (journal D-286).
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from cinoc.evaluation._alignment import (
    aligned_to_reference,
    alignment,
    char_counts,
    opcodes,
)
from cinoc.evaluation.analysis import DocumentHallucinationPayload
from cinoc.evaluation.diagnostics import char_confusions, line_cers
from cinoc.evaluation.document_hallucination import DocumentHallucinationCollector
from cinoc.evaluation.taxonomy import classify_texts, classify_word_pair
from cinoc.evaluation.textual_fidelity import modernization_counts, tokenize
from cinoc.evaluation.word_errors import word_misses

jiwer = pytest.importorskip("jiwer")

_BNL_MINI = Path(__file__).parents[1] / "fixtures" / "reference_corpus" / "bnl_mini"

#: Article bégayé : le cas où ``difflib`` diverge (2 lacunes + 3 insertions).
_BEGAIEMENT = ("le roi le roi le roi", "le roi le le roi le roi")

#: Cas construits sans fusion ni scission possible : vocabulaire sans préfixe
#: commun, donc deux suites de mots distinctes ne se concatènent jamais pareil.
_CAS = [
    _BEGAIEMENT,
    ("de la ville de la cour de France", "la ville de la de cour de France"),
    ("le roi de France", "le roi de France"),
    ("le roi de France", ""),
    ("", "le roi"),
    ("le roi", "le roi de la cour de France et"),
    ("et de la et de la et", "et de et la de la et"),
]


def _jiwer_counts(reference: str, hypothesis: str) -> tuple[int, int, int]:
    """``(S, D, I)`` de jiwer au mot, sur la découpe ``str.split`` du WER."""
    ref, hyp = reference.split(), hypothesis.split()
    if not ref:
        return 0, 0, len(hyp)
    if not hyp:
        return 0, len(ref), 0
    out = jiwer.process_words(" ".join(ref), " ".join(hyp))
    return out.substitutions, out.deletions, out.insertions


def _jiwer_segmentation(reference: str, hypothesis: str) -> tuple[int, int]:
    """``(D, I)`` que jiwer place dans des blocs d'éditions fusion/scission.

    Bloc = éditions contiguses (entre deux ``equal``) dont les deux côtés se
    concatènent à l'identique : la taxonomie les range en ``segmentation``.
    Recalculé ici sur l'alignement de jiwer, pas sur celui de Cinoc.
    """
    ref, hyp = reference.split(), hypothesis.split()
    if not ref or not hyp:
        return 0, 0
    chunks = jiwer.process_words(" ".join(ref), " ".join(hyp)).alignments[0]
    deletions = insertions = 0
    run: list[object] = []
    for chunk in [*chunks, None]:
        if chunk is not None and chunk.type != "equal":
            run.append(chunk)
            continue
        if run:
            r0, r1 = run[0].ref_start_idx, run[-1].ref_end_idx  # type: ignore[attr-defined]
            h0, h1 = run[0].hyp_start_idx, run[-1].hyp_end_idx  # type: ignore[attr-defined]
            if "".join(ref[r0:r1]) == "".join(hyp[h0:h1]):
                deletions += sum(
                    c.ref_end_idx - c.ref_start_idx  # type: ignore[attr-defined]
                    for c in run if c.type == "delete"  # type: ignore[attr-defined]
                )
                insertions += sum(
                    c.hyp_end_idx - c.hyp_start_idx  # type: ignore[attr-defined]
                    for c in run if c.type == "insert"  # type: ignore[attr-defined]
                )
            run = []
    return deletions, insertions


def _bnl_mini_pairs() -> list[tuple[str, str]]:
    pairs = []
    for gt in sorted(_BNL_MINI.glob("*.gt.txt")):
        reference = gt.read_text(encoding="utf-8")
        stem = gt.name.removesuffix(".gt.txt")
        for hyp in sorted(_BNL_MINI.glob(f"{stem}.*.txt")):
            if hyp != gt:
                pairs.append((reference, hyp.read_text(encoding="utf-8")))
    return pairs


# --- taxonomie : les lacunes sont les D du WER --------------------------------


@pytest.mark.parametrize(("reference", "hypothesis"), _CAS)
def test_taxonomie_lacunes_egales_aux_suppressions_du_wer(
    reference: str, hypothesis: str
) -> None:
    counts = classify_texts(reference, hypothesis)
    substitutions, deletions, insertions = _jiwer_counts(reference, hypothesis)
    assert counts["segmentation"] == 0
    assert counts["lacuna"] == deletions
    assert counts["insertion"] == insertions
    assert sum(counts.values()) == substitutions + deletions + insertions


def test_taxonomie_begaiement_une_seule_insertion() -> None:
    assert classify_texts(*_BEGAIEMENT) == Counter({"insertion": 1})


def test_taxonomie_partitionne_les_editions_du_wer_sur_bnl_mini() -> None:
    """Sur de l'OCR réel (5 moteurs × pages BNL), chaque édition du WER a une
    classe et une seule : les lacunes sont les D hors fusion/scission, les
    insertions les I hors fusion/scission, et le total vaut S + D + I."""
    pairs = _bnl_mini_pairs()
    assert len(pairs) > 100
    for reference, hypothesis in pairs:
        counts = classify_texts(reference, hypothesis)
        substitutions, deletions, insertions = _jiwer_counts(reference, hypothesis)
        seg_d, seg_i = _jiwer_segmentation(reference, hypothesis)
        assert counts["lacuna"] == deletions - seg_d
        assert counts["insertion"] == insertions - seg_i
        assert sum(counts.values()) == substitutions + deletions + insertions


def test_taxonomie_aleatoire_contre_jiwer() -> None:
    rng = random.Random(286)
    mots = ("le", "roi", "de", "France", "et", "la", "cour")
    for _ in range(300):
        reference = " ".join(rng.choice(mots) for _ in range(rng.randint(0, 9)))
        hypothesis = " ".join(rng.choice(mots) for _ in range(rng.randint(0, 9)))
        counts = classify_texts(reference, hypothesis)
        substitutions, deletions, insertions = _jiwer_counts(reference, hypothesis)
        assert counts["lacuna"] == deletions, (reference, hypothesis)
        assert counts["insertion"] == insertions, (reference, hypothesis)
        assert sum(counts.values()) == substitutions + deletions + insertions


# --- taxonomie : I majuscule lu l minuscule ----------------------------------


def test_taxonomie_i_majuscule_lu_l_est_visuel() -> None:
    # La table visuelle était appliquée après ``lower()`` : ``I`` y était
    # déjà devenu ``i``, et la règle ``I→l`` ne servait jamais.
    assert classify_word_pair("Il", "ll") == "visual"
    assert classify_word_pair("I'Alzette", "l'Alzette") == "visual"
    assert classify_word_pair("III", "lll") == "visual"
    # Les confusions déjà vues en minuscule le restent, majuscules comprises.
    assert classify_word_pair("MAIN", "RNAIN") == "visual"
    assert classify_word_pair("il", "i1") == "visual"


# --- mots manqués et modernisation : les mêmes D ------------------------------


@pytest.mark.parametrize(("reference", "hypothesis"), _CAS)
def test_mots_manques_et_modernisation_suivent_le_wer(
    reference: str, hypothesis: str
) -> None:
    ref_tokens = " ".join(tokenize(reference))
    hyp_tokens = " ".join(tokenize(hypothesis))
    substitutions, deletions, _ = _jiwer_counts(ref_tokens, hyp_tokens)
    misses = word_misses(reference, hypothesis)
    assert sum(1 for _, form in misses if form == "∅") == deletions
    assert len(misses) == substitutions + deletions
    slots = modernization_counts(reference, hypothesis)
    assert sum(s.n_modernized for s in slots.values()) == substitutions + deletions
    assert sum(s.n_total for s in slots.values()) == len(tokenize(reference))


def test_mots_manques_begaiement_aucun_rate() -> None:
    # Le mot en trop est une insertion : aucun mot GT n'est raté.
    assert word_misses(*_BEGAIEMENT) == []


# --- hallucinations : un passage inséré, pas une sortie brouillée -------------


def _hallucinations(reference: str, hypothesis: str) -> list[str]:
    collector = DocumentHallucinationCollector()
    collector.observe("p", "d", reference, hypothesis)
    analysis = collector.build("texte")
    if analysis is None:
        return []
    payload = analysis.payload
    assert isinstance(payload, DocumentHallucinationPayload)
    return [b.text for d in payload.documents for p in d.pipelines for b in p.blocks]


def test_sortie_brouillee_n_est_pas_une_hallucination() -> None:
    # Sept mots tous mal lus, dont un tombe sur un mot GT ailleurs : l'optimal
    # est sept substitutions ; ``difflib`` ancrait « de » et voyait six mots
    # insérés.
    gt = "alpha beta gamma delta epsilon zeta de"
    sortie = "de alfa bta gama dlta epsilom zta"
    assert _hallucinations(gt, sortie) == []


def test_passage_insere_apres_un_mot_mal_lu_est_signale() -> None:
    # « ville » lu « vile » puis quatre mots ajoutés : ``difflib`` en faisait
    # un seul remplacement 1 → 5, jamais signalé. L'optimal est une
    # substitution et quatre insertions ; ``rapidfuzz`` seul insérait
    # « vile puis vint une » et substituait « ville » ↔ « inondation » — le
    # départage par ressemblance garde « ville » ↔ « vile ».
    gt = "le budget de la ville est vote"
    sortie = "le budget de la vile puis vint une inondation est vote"
    assert _hallucinations(gt, sortie) == ["puis vint une inondation"]


# --- confusions de caractères : les substitutions du CER ----------------------


@pytest.mark.parametrize(
    ("reference", "hypothesis"),
    [
        ("le roi de France", "le rai de Franee"),
        ("le le", "la le"),
        ("cheval blanc", "cheual blane"),
        ("main", "rnain"),
    ],
)
def test_confusions_sont_les_substitutions_du_cer(
    reference: str, hypothesis: str
) -> None:
    pairs = char_confusions(reference, hypothesis)
    assert sum(pairs.values()) == char_counts(reference, hypothesis)[0]


def test_confusions_hand_derived() -> None:
    assert char_confusions("le roi de France", "le rai de Franee") == Counter(
        {("o", "a"): 1, ("c", "e"): 1}
    )


def test_confusions_sur_bnl_mini_egales_au_s_du_cer() -> None:
    for reference, hypothesis in _bnl_mini_pairs()[:40]:
        pairs = char_confusions(reference, hypothesis)
        assert sum(pairs.values()) == char_counts(reference, hypothesis)[0]


# --- pires lignes : appariées par F15 ----------------------------------------


def test_pires_lignes_ligne_inseree_ne_decale_pas_les_suivantes() -> None:
    reference = "premiere ligne\ndeuxieme ligne\ntroisieme ligne"
    hypothesis = "en-tete parasite\npremiere ligne\ndeuxieme ligne\ntroisieme ligne"
    assert [cer for _, cer, _, _ in line_cers(reference, hypothesis)] == [0.0] * 3


def test_pires_lignes_ligne_perdue_vaut_un() -> None:
    reference = "premiere ligne\ndeuxieme ligne\ntroisieme ligne"
    hypothesis = "premiere ligne\ntroisieme ligne"
    assert line_cers(reference, hypothesis) == [
        (0, 0.0, "premiere ligne", "premiere ligne"),
        (1, 1.0, "deuxieme ligne", ""),
        (2, 0.0, "troisieme ligne", "troisieme ligne"),
    ]


# --- le helper : optimal, et stable d'une graine de hachage à l'autre ---------


def test_opcodes_cout_minimal() -> None:
    cost = sum(
        max(op.src_end - op.src_start, op.dest_end - op.dest_start)
        for op in opcodes(_BEGAIEMENT[0].split(), _BEGAIEMENT[1].split())
        if op.tag != "equal"
    )
    assert cost == 1


def _counts(
    pairs: list[tuple[int | None, int | None]], ref: list[str], hyp: list[str]
) -> tuple[int, int, int, int]:
    matched = [(i, j) for i, j in pairs if i is not None and j is not None]
    hits = sum(1 for i, j in matched if ref[i] == hyp[j])  # type: ignore[index]
    subs = len(matched) - hits
    dels = sum(1 for _, j in pairs if j is None)
    ins = sum(1 for i, _ in pairs if i is None)
    return hits, subs, dels, ins


def test_alignment_garde_les_comptes_du_wer_et_apparie_par_ressemblance() -> None:
    ref = "den Schichtmeister übergehen Sie nicht!".split()
    hyp = "den Schichtmeiſter - übergehen: Sie’ nicht!".split()
    # ``rapidfuzz`` seul : « Schichtmeiſter » inséré, « Schichtmeister » ↔ « - ».
    assert [(ref[i] if i is not None else None, hyp[j] if j is not None else None)
            for i, j in alignment(ref, hyp)] == [
        ("den", "den"),
        ("Schichtmeister", "Schichtmeiſter"),
        (None, "-"),
        ("übergehen", "übergehen:"),
        ("Sie", "Sie’"),
        ("nicht!", "nicht!"),
    ]
    rng = random.Random(14)
    mots = ("roi", "roy", "rois", "de", "la", "le", "France", "Franee")
    for _ in range(300):
        ref = [rng.choice(mots) for _ in range(rng.randint(0, 8))]
        hyp = [rng.choice(mots) for _ in range(rng.randint(0, 8))]
        pairs = alignment(ref, hyp)
        assert [i for i, _ in pairs if i is not None] == list(range(len(ref)))
        assert [j for _, j in pairs if j is not None] == list(range(len(hyp)))
        hits = subs = dels = ins = 0
        for op in opcodes(ref, hyp):
            n_ref, n_hyp = op.src_end - op.src_start, op.dest_end - op.dest_start
            hits += n_ref if op.tag == "equal" else 0
            subs += n_ref if op.tag == "replace" else 0
            dels += n_ref if op.tag == "delete" else 0
            ins += n_hyp if op.tag == "insert" else 0
        assert _counts(pairs, ref, hyp) == (hits, subs, dels, ins)


def test_aligned_to_reference_hand_derived() -> None:
    assert aligned_to_reference(["a", "b", "c"], ["x", "a", "c"]) == ["a", None, "c"]
    assert aligned_to_reference([], ["a"]) == []


_SONDE = """
import json, sys
from pathlib import Path
from cinoc.evaluation.analysis import DocumentHallucinationPayload
from cinoc.evaluation.diagnostics import char_confusions, line_cers
from cinoc.evaluation.taxonomy import classify_texts
from cinoc.evaluation.word_errors import word_misses
from cinoc.evaluation._alignment import alignment, opcodes
pairs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
out = []
for ref, hyp in pairs:
    out.append([
        sorted(classify_texts(ref, hyp).items()),
        word_misses(ref, hyp),
        sorted(["".join(k), v] for k, v in char_confusions(ref, hyp).items()),
        line_cers(ref, hyp),
        [tuple(op) for op in opcodes(ref.split(), hyp.split())],
        alignment(ref.split(), hyp.split()),
    ])
sys.stdout.write(json.dumps(out, ensure_ascii=True))
"""


def test_alignement_identique_sous_deux_graines_de_hachage(tmp_path: Path) -> None:
    """Les égalités de coût se tranchent pareil quelle que soit la graine :
    les mots sont codés en entiers par ordre d'apparition, jamais par
    ``hash()``."""
    cases = tmp_path / "cases.json"
    cases.write_text(
        json.dumps([*_CAS, *_bnl_mini_pairs()[:20]], ensure_ascii=False),
        encoding="utf-8",
    )
    sorties = {
        subprocess.run(
            [sys.executable, "-c", _SONDE, str(cases)],
            check=True,
            capture_output=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("0", "3", "4242")
    }
    assert len(sorties) == 1
