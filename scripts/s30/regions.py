import json,glob,os,sys
from PIL import Image
arch, corpus_dir, out = sys.argv[1:4]
seen={}
for idx in glob.glob(f"{arch}/*/index.json"):
    d=json.load(open(idx))
    for e in d["steps"]:
        if e["step"]=="seg" and "layout" in e["artifacts"]:
            a=e["artifacts"]["layout"]; doc=a["document_id"]
            if doc not in seen:
                seen[doc]=json.load(open(os.path.join(os.path.dirname(idx),a["uri"])))
def leaves(regs):
    for r in regs:
        if r.get("regions"): yield from leaves(r["regions"])
        else: yield r
pages=[]
for doc,lay in sorted(seen.items()):
    p=lay["pages"][0]
    regs=[(r["geometry"]["bbox"]["width"],r["geometry"]["bbox"]["height"]) for r in leaves(p["regions"]) if r.get("geometry") and r["geometry"].get("bbox")]
    pages.append({"doc":doc,"w":p["width"],"h":p["height"],"regions":regs})
json.dump(pages,open(out,"w"))
print(len(pages), sum(len(p["regions"]) for p in pages))
