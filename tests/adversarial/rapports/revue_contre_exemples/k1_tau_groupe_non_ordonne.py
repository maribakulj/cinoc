"""K1 table « Ordre de lecture » : S = (paires discordantes, paires ORDONNÉES PAR
LA RÉFÉRENCE) ; M5 ; §2.4 « Elle respecte reading_order imbriqué ».

Le `CanonicalLayout` existant ne sait pas quelles paires la référence ordonne :
`LayoutPage.reading_order` est une liste plate (`domain/layout.py:111`) et
`ReadingOrderGroup.flatten()` (`formats/pagexml/types.py:44`) efface
`UnorderedGroup`. Deux marginalia déclarées NON ordonnées par la VT deviennent
une paire ordonnée, et l'ordre inverse est compté comme discordance.
"""
from cinoc.formats.pagexml.parser import parse_pagexml
from cinoc.formats.pagexml.layout_map import page_to_layout
from cinoc.evaluation.reading_order import kendall_distance

NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
def page(order_xml):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="{NS}"><Metadata><Creator>t</Creator><Created>2020-01-01T00:00:00</Created><LastChange>2020-01-01T00:00:00</LastChange></Metadata>
<Page imageFilename="x.png" imageWidth="100" imageHeight="100">
<ReadingOrder>{order_xml}</ReadingOrder>
<TextRegion id="m1"><Coords points="0,0 10,0 10,10 0,10"/></TextRegion>
<TextRegion id="m2"><Coords points="20,0 30,0 30,10 20,10"/></TextRegion>
</Page></PcGts>""".encode()

gt = page('<UnorderedGroup id="g"><RegionRef index="0" regionRef="m1"/><RegionRef index="1" regionRef="m2"/></UnorderedGroup>')
doc = parse_pagexml(gt)
print("groupe parsé : ordered =", doc.pages[0].reading_order.ordered)
layout = page_to_layout(doc)
flat = layout.pages[0].reading_order
print("CanonicalLayout.reading_order =", flat, "(l'information « non ordonné » a disparu)")
d = kendall_distance(list(flat), ["m2", "m1"])
print("distance de Kendall pour l'hypothèse (m2, m1) :", d)
assert doc.pages[0].reading_order.ordered is False and d == 1.0
print("=> attendu : aucune paire ordonnée par la référence (τ non défini, 'no_pairs').")
