"""Add a smooth fade slide-transition to every slide of PRESENTATION.pptx.
pptxgenjs has no transition/animation API, so we inject the OOXML directly.
Run AFTER `node build.js`."""
import os
import re
import zipfile

SRC = os.path.join(os.path.dirname(__file__), "..", "PRESENTATION.pptx")
TMP = SRC + ".tmp"
# Classic, widely-supported fade. `spd="med"` = medium speed.
TRANS = '<p:transition spd="med"><p:fade/></p:transition>'

zin = zipfile.ZipFile(SRC, "r")
zout = zipfile.ZipFile(TMP, "w", zipfile.ZIP_DEFLATED)
n = 0
for item in zin.infolist():
    data = zin.read(item.filename)
    if re.match(r"ppt/slides/slide\d+\.xml$", item.filename):
        txt = data.decode("utf-8")
        if "<p:transition" not in txt and "</p:sld>" in txt:
            # transition belongs after cSld+clrMapOvr, before </p:sld> (no timing present)
            txt = txt.replace("</p:sld>", TRANS + "</p:sld>")
            n += 1
        data = txt.encode("utf-8")
    zout.writestr(item, data)
zin.close()
zout.close()
os.replace(TMP, SRC)
print(f"fade transition added to {n} slides")
