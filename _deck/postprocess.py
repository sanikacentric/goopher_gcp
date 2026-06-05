"""Post-process PRESENTATION.pptx (pptxgenjs has no transition/animation API):
  1. add a smooth fade SLIDE TRANSITION to every slide, and
  2. add ELEMENT BUILD animations (cards fade in one-by-one on click) to the
     card-grid slides.
Run AFTER `node build.js`.  Idempotent.
"""
import os
import re
import zipfile

SRC = os.path.join(os.path.dirname(__file__), "..", "PRESENTATION.pptx")
TMP = SRC + ".tmp"

TRANS = '<p:transition spd="med"><p:fade/></p:transition>'

# Per-slide build config: skip the first N shapes (kicker+title), then fade in
# the next `groups*chunk` shapes in `chunk`-sized clicks. Trailing shapes (e.g.
# the footer's 2 text boxes) are left static. chunk = shapes per card.
ANIM = {
    6:  dict(skip=2, chunk=5, groups=6),   # Inside the platform (6 panels)
    8:  dict(skip=2, chunk=5, groups=4),   # Four requirements (4 cards)
    10: dict(skip=2, chunk=6, groups=6),   # Challenges (6 cards, 6 shapes each)
    11: dict(skip=2, chunk=5, groups=6),   # Wow factor (6 cards)
    12: dict(skip=2, chunk=5, groups=6),   # Reliability (6 cards)
    15: dict(skip=2, chunk=5, groups=6),   # Learnings (6 cards)
}


def ordered_spids(xml):
    """Top-level shape ids (sp/pic/graphicFrame/cxnSp) in spTree order."""
    return [int(i) for _, i in
            re.findall(r"<p:(sp|pic|graphicFrame|cxnSp)>.*?<p:cNvPr id=\"(\d+)\"", xml, re.S)]


def build_timing(groups):
    """groups = list of lists of spids; each inner list fades in together on one
    click, groups advance click-by-click. Returns a <p:timing> string."""
    nid = [2]  # cTn ids 1 (tmRoot) & 2 (mainSeq) are reserved

    def newid():
        nid[0] += 1
        return nid[0]

    def shape_effect(spid, first):
        c1, c2, c3 = newid(), newid(), newid()
        node = (
            f'<p:par><p:cTn id="{c1}" presetID="10" presetClass="entr" presetSubtype="0" '
            f'fill="hold" grpId="0" nodeType="{"clickEffect" if first else "withEffect"}">'
            '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
            f'<p:set><p:cBhvr><p:cTn id="{c2}" dur="1" fill="hold">'
            '<p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
            f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
            '<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
            '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
            '<p:animEffect transition="in" filter="fade"><p:cBhvr>'
            f'<p:cTn id="{c3}" dur="500"/><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'
            '</p:cBhvr></p:animEffect></p:childTnLst></p:cTn></p:par>'
        )
        return node

    def click_group(spids):
        a, b = newid(), newid()
        effects = "".join(shape_effect(sp, k == 0) for k, sp in enumerate(spids))
        return (
            f'<p:par><p:cTn id="{a}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/>'
            f'</p:stCondLst><p:childTnLst><p:par><p:cTn id="{b}" fill="hold">'
            '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
            f'{effects}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>'
        )

    seq = "".join(click_group(g) for g in groups)
    return (
        '<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" '
        'nodeType="tmRoot"><p:childTnLst><p:seq concurrent="1" nextAc="seek">'
        f'<p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>{seq}'
        '</p:childTnLst></p:cTn>'
        '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
        '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
        '</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>'
    )


zin = zipfile.ZipFile(SRC, "r")
zout = zipfile.ZipFile(TMP, "w", zipfile.ZIP_DEFLATED)
trans_n = anim_n = 0
for item in zin.infolist():
    data = zin.read(item.filename)
    m = re.match(r"ppt/slides/slide(\d+)\.xml$", item.filename)
    if m and "</p:sld>" in data.decode("utf-8", "ignore"):
        idx = int(m.group(1))
        txt = data.decode("utf-8")
        add = ""
        if "<p:transition" not in txt:
            add += TRANS
            trans_n += 1
        cfg = ANIM.get(idx)
        if cfg and "<p:timing" not in txt:
            spids = ordered_spids(txt)
            need = cfg["skip"] + cfg["chunk"] * cfg["groups"]
            if len(spids) >= need:
                chosen = spids[cfg["skip"]: need]
                groups = [chosen[i:i + cfg["chunk"]] for i in range(0, len(chosen), cfg["chunk"])]
                add += build_timing(groups)
                anim_n += 1
            else:
                print(f"  slide{idx}: shape count {len(spids)} < {need} — skipped animation")
        txt = txt.replace("</p:sld>", add + "</p:sld>")
        data = txt.encode("utf-8")
    zout.writestr(item, data)
zin.close()
zout.close()
os.replace(TMP, SRC)
print(f"fade transition on {trans_n} slides; build animation on {anim_n} slides")
