"""Tests de la normalisation de comparaison."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cinoc.formats.text.normalization import (
    NORMALIZATION_PROFILES,
    NormalizationProfile,
    get_builtin_profile,
)

# --- ordre canonique : caseless × table (correction du bug D8) --------------


def test_caseless_table_neutralizes_case_on_uppercase() -> None:
    """Sous caseless, une table à clés minuscules doit s'appliquer AUSSI au
    texte majuscule : casefold précède la table + clés casefoldées."""
    prof = NormalizationProfile(name="t", caseless=True, diplomatic_table={"u": "v"})
    assert prof.normalize("Uu") == "vv"


def test_caseless_table_folds_values_too() -> None:
    prof = NormalizationProfile(name="t", caseless=True, diplomatic_table={"&": "ET"})
    assert prof.normalize("A&B") == "aetb"


# --- substitution mono-passe (audit F12) ------------------------------------


def test_single_pass_swap_uv() -> None:
    """``{u:v, v:u}`` sur ``"uv"`` → ``"vu"`` (pas de cascade ``"vv"``/``"uu"``)."""
    prof = NormalizationProfile(name="swap", diplomatic_table={"u": "v", "v": "u"})
    assert prof.normalize("uv") == "vu"


def test_longest_key_wins() -> None:
    prof = NormalizationProfile(name="lk", diplomatic_table={"vv": "w", "v": "u"})
    assert prof.normalize("vv") == "w"


# --- symétrie GT/OCR (audit F11) --------------------------------------------


def test_symmetry_same_transform_both_sides() -> None:
    prof = get_builtin_profile("medieval_french")
    gt, ocr = "ſuper uiuit", "super vivit"
    assert prof.normalize(gt) == prof.normalize(ocr)


# --- hygiène (caractères invisibles) ----------------------------------------


@pytest.mark.parametrize("invisible", ["­", "​", "﻿", "‎"])
def test_strips_invisible_chars(invisible: str) -> None:
    prof = NormalizationProfile(name="h", unicode_form="none")
    assert prof.normalize(f"a{invisible}b") == "ab"


def test_keeps_newline_and_tab() -> None:
    prof = NormalizationProfile(name="h", unicode_form="none")
    assert prof.normalize("a\tb\nc") == "a\tb\nc"


# --- formes unicode ----------------------------------------------------------


def test_nfc_recomposes() -> None:
    prof = get_builtin_profile("nfc")
    assert prof.normalize("e" + "́") == "é"  # décomposé → NFC


def test_nfkc_resolves_ligature() -> None:
    prof = get_builtin_profile("nfkc")
    assert prof.normalize("ﬁn") == "fin"  # ﬁ → fi


# --- diacritiques ------------------------------------------------------------


def test_strip_diacritics() -> None:
    out = get_builtin_profile("no_diacritics").normalize("élève à")
    assert out == "eleve a"


# --- espaces -----------------------------------------------------------------


def test_flat_collapses_newlines_and_spaces() -> None:
    out = get_builtin_profile("flat_text").normalize("le chat\nnoir")
    assert out == "le chat noir"


def test_intra_line_keeps_newlines() -> None:
    out = get_builtin_profile("keep_line_breaks").normalize("le  chat\nnoir")
    assert out == "le chat\nnoir"


def test_flat_collapses_nbsp() -> None:
    out = get_builtin_profile("flat_text").normalize("a b")
    assert out == "a b"


# --- exclusion ---------------------------------------------------------------


def test_no_punctuation_replaces_with_space() -> None:
    out = get_builtin_profile("no_punctuation").normalize("Pierre,fils")
    assert out == "Pierre fils"


def test_no_apostrophes_deletes() -> None:
    assert get_builtin_profile("no_apostrophes").normalize("l’ami") == "lami"


def test_exclude_chars_string_is_set_no_magic_separator() -> None:
    """``", "`` = ensemble {virgule, espace} — aucun découpage magique."""
    prof = NormalizationProfile(name="e", exclude_chars=", ", exclude_mode="delete")
    assert prof.exclude_chars == frozenset({",", " "})


def test_exclude_ignores_multichar_items() -> None:
    prof = NormalizationProfile(name="e", exclude_chars=["ab", "x"])
    assert prof.exclude_chars == frozenset({"x"})


# --- sérialisation & construction -------------------------------------------


def test_as_dict_is_deterministic_and_sorted() -> None:
    prof = NormalizationProfile(
        name="d", diplomatic_table={"u": "v", "i": "j"}, exclude_chars="ba"
    )
    d = prof.as_dict()
    assert d["exclude_chars"] == ["a", "b"]
    assert list(d["diplomatic_table"]) == ["i", "u"]


@pytest.mark.parametrize("ancienne_cle", ["nfc: false", "diplomatic:\n  ſ: s"])
def test_the_legacy_keys_are_refused_not_translated(ancienne_cle: str) -> None:
    """Le sucre ``nfc: bool`` → ``unicode_form`` et l'alias ``diplomatic`` de
    ``diplomatic_table`` n'avaient aucun consommateur (audit D-264) : retirés
    (D-301). Une clé d'avant est refusée comme toute clé inconnue — jamais
    traduite en silence."""
    with pytest.raises(ValidationError):
        NormalizationProfile.from_yaml_text(f"name: x\n{ancienne_cle}\n")


def test_no_file_loader_nor_dict_shim_remains() -> None:
    """``from_yaml`` (lecture d'un chemin) n'avait que des tests pour client, et
    ``from_dict`` que ``from_yaml_text`` : une seule entrée reste, le texte."""
    assert not hasattr(NormalizationProfile, "from_yaml")
    assert not hasattr(NormalizationProfile, "from_dict")


def test_from_yaml_text_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError):
        NormalizationProfile.from_yaml_text("name: x\ndiplomatik:\n  ſ: s\n")


def test_from_yaml_text_roundtrip() -> None:
    prof = NormalizationProfile.from_yaml_text(
        "name: custom\ncaseless: true\ndiplomatic_table:\n  ſ: s\n"
    )
    assert prof.name == "custom" and prof.caseless
    assert prof.diplomatic_table == {"ſ": "s"}
    assert NormalizationProfile.from_yaml_text("caseless: true\n").name == "custom"


# --- profils & invariants ----------------------------------------------------


def test_exactly_fifteen_profiles() -> None:
    """12 profils retenus à la couche 2, les 2 profils de conformité HIPE
    (``hipe``/``heritage``, D-115), et ``dehyphenated``.

    ``dehyphenated`` est un profil de **comparaison**, ajouté quand un
    correcteur qui recolle les mots coupés est devenu mesurable : sans lui, il
    est pénalisé pour avoir bien fait (CER 0,1179 contre 0,1119 sur
    ``corpus/37-GT-BNL``). Il ne fait pas baisser l'erreur par lui-même.
    """
    assert len(NORMALIZATION_PROFILES) == 15
    assert "dehyphenated" in NORMALIZATION_PROFILES


def test_no_english_profiles() -> None:
    assert not any(
        n in NORMALIZATION_PROFILES
        for n in ("early_modern_english", "medieval_english", "secretary_hand")
    )


def test_default_profile_is_neutral() -> None:
    nfc = get_builtin_profile("nfc")
    assert not nfc.diplomatic_table and not nfc.caseless
    assert nfc.unicode_form == "NFC"


@pytest.mark.parametrize("name", sorted(NORMALIZATION_PROFILES))
def test_profile_is_idempotent(name: str) -> None:
    prof = NORMALIZATION_PROFILES[name]
    once = prof.normalize("Élève: ſuper, l’ami\nvit  vv.")
    assert prof.normalize(once) == once


def test_profiles_are_frozen() -> None:
    with pytest.raises(ValidationError):
        get_builtin_profile("nfc").caseless = True  # type: ignore[misc]


def test_unknown_profile_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        get_builtin_profile("does_not_exist")


def test_invalid_unicode_form_rejected() -> None:
    with pytest.raises(ValidationError):
        NormalizationProfile(name="bad", unicode_form="NFG")  # type: ignore[arg-type]
