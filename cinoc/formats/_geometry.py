"""Primitives géométriques partagées par les formats (points numériques).

Les coordonnées sont des entiers en pixels (convention ALTO et PAGE). On conserve
les valeurs négatives (une région peut déborder la page) ; la réconciliation
d'unités/résolution est une affaire de couche 3.
"""

from __future__ import annotations

Point = tuple[int, int]


def parse_points(raw: str) -> tuple[Point, ...]:
    """Parse une liste de points ALTO/PAGE, **dans ses deux écritures**.

    Le schéma ALTO v4 (``PointsType``) admet explicitement les deux, et le dit :

    * ``"x1,y1 x2,y2 …"`` — « hautement recommandée, largement utilisée » ;
    * ``"x1 y1 x2 y2 …"`` — « conservée pour compatibilité, car des outils
      l'utilisent actuellement ».

    N'accepter que la première paraît rigoureux et ne l'est pas : c'est refuser
    un fichier conforme. Le premier outil réellement branché — ``kraken``, qui
    écrit la seconde — a vu **toute** sa géométrie jetée, avec un simple
    avertissement dans le journal et des régions sans coordonnées en sortie.

    Lève ``ValueError`` si la chaîne n'est ni l'une ni l'autre ; le caller
    décide d'ignorer la géométrie plutôt que de planter.
    """
    jetons = raw.split()
    if not jetons:
        raise ValueError("aucun point")
    # Le séparateur décide de l'écriture. On ne devine pas jeton par jeton : un
    # mélange des deux n'est pas conforme, et l'accepter masquerait un fichier
    # réellement abîmé.
    if any("," in jeton for jeton in jetons):
        return tuple(_paire(jeton) for jeton in jetons)
    if len(jetons) % 2:
        raise ValueError(
            f"liste plate de longueur impaire ({len(jetons)} nombres) : "
            "les coordonnées ne s'apparient pas"
        )
    try:
        nombres = [int(float(jeton)) for jeton in jetons]
    except ValueError as exc:
        raise ValueError(f"nombre illisible dans {raw[:40]!r}") from exc
    return tuple(zip(nombres[::2], nombres[1::2], strict=True))


def _paire(jeton: str) -> Point:
    x_str, virgule, y_str = jeton.partition(",")
    if not virgule or not x_str or not y_str:
        raise ValueError(f"point malformé : {jeton!r}")
    try:
        return (int(float(x_str)), int(float(y_str)))
    except ValueError as exc:
        raise ValueError(f"point malformé : {jeton!r}") from exc


def format_points(points: tuple[Point, ...]) -> str:
    """Sérialise des points en ``"x1,y1 x2,y2 ..."`` (déterministe)."""
    return " ".join(f"{x},{y}" for x, y in points)
