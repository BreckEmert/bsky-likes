# -*- coding: utf-8 -*-
"""Build topic_legend.json: tier-1 topic id -> {name, tab10 color}. Used to
color the map by topic ('Topics' color mode) + render the legend. Matches the
saved names (names_reference.json) to the current clusters by likee overlap."""
import json
from bsky_likes import config

ref = json.load(open("names_reference.json", encoding="utf-8"))["tier1"]
ctx = {x["id"]: x for x in json.load(open("cluster_context_t1.json", encoding="utf-8"))}

names = {r["name"]: set(r["top_likes"]) for r in ref}
pairs = []
for cid, c in ctx.items():
    L = set(b["handle"] for b in c["likes"][:14])
    for nm, tl in names.items():
        pairs.append((len(L & tl), cid, nm))
pairs.sort(reverse=True)
cd, nd, id2name = set(), set(), {}
for ov, cid, nm in pairs:
    if cid in cd or nm in nd:
        continue
    id2name[cid] = nm; cd.add(cid); nd.add(nm)

# vivid-but-professional palette (matplotlib tab10)
TAB10 = [[31,119,180],[255,127,14],[44,160,44],[214,39,40],[148,103,189],
         [140,86,75],[227,119,194],[127,127,127],[188,189,34],[23,190,207]]
order = sorted(ctx, key=lambda c: -ctx[c]["size"])     # biggest topic -> blue
legend = [{"id": int(cid), "name": id2name.get(cid, f"Topic {cid}"),
           "color": TAB10[rank % len(TAB10)], "size": ctx[cid]["size"]}
          for rank, cid in enumerate(order)]
out = json.dumps(legend, ensure_ascii=False)
open("topic_legend.json", "w", encoding="utf-8").write(out)
(config.PROJECT_DIR.parent / "site" / "public" / "explore" / "topic_legend.json").write_text(out, encoding="utf-8")
print("topic_legend.json:")
for L in legend:
    print(f"  id={L['id']} {L['color']} {L['name']} ({L['size']:,})")
