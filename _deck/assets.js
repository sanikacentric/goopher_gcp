// Generate premium background + brand mark + icon PNGs for the GOOPHER deck.
const fs = require("fs");
const sharp = require("sharp");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const Fa = require("react-icons/fa");

async function svgToPng(svg, file) {
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  fs.writeFileSync(file, buf);
}

const BG_DARK = `
<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0A0E1F"/>
      <stop offset="55%" stop-color="#120E29"/>
      <stop offset="100%" stop-color="#1A0F2E"/>
    </linearGradient>
    <radialGradient id="glow" cx="80%" cy="14%" r="60%">
      <stop offset="0%" stop-color="#7C3AED" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="#7C3AED" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow2" cx="8%" cy="94%" r="55%">
      <stop offset="0%" stop-color="#E11D48" stop-opacity="0.42"/>
      <stop offset="100%" stop-color="#E11D48" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1600" height="900" fill="url(#g)"/>
  <rect width="1600" height="900" fill="url(#glow)"/>
  <rect width="1600" height="900" fill="url(#glow2)"/>
</svg>`;

// Brand tile: gradient rounded square with a white speech-bubble + spark.
const LOGO = `
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#E11D48"/>
      <stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>
  <path d="M70 78 h116 a22 22 0 0 1 22 22 v58 a22 22 0 0 1 -22 22 h-58 l-34 30 v-30 h-2 a22 22 0 0 1 -22 -22 v-58 a22 22 0 0 1 22 -22 z"
        fill="#FFFFFF" opacity="0.96"/>
  <circle cx="104" cy="129" r="9" fill="#7C3AED"/>
  <circle cx="138" cy="129" r="9" fill="#E11D48"/>
  <circle cx="172" cy="129" r="9" fill="#0D9488"/>
</svg>`;

async function iconPng(IconComponent, color, file, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
  await svgToPng(svg, file);
}

(async () => {
  await svgToPng(BG_DARK, "bg_dark.png");
  await svgToPng(LOGO, "logo.png");

  // icon name -> [component, hexcolor]
  const icons = {
    robot:   [Fa.FaRobot, "#7C3AED"],
    comments:[Fa.FaComments, "#7C3AED"],
    mic:     [Fa.FaMicrophone, "#E11D48"],
    camera:  [Fa.FaCamera, "#E11D48"],
    globe:   [Fa.FaGlobe, "#2563EB"],
    mobile:  [Fa.FaMobileAlt, "#2563EB"],
    layers:  [Fa.FaLayerGroup, "#0D9488"],
    shield:  [Fa.FaShieldAlt, "#7C3AED"],
    lock:    [Fa.FaLock, "#0D9488"],
    sitemap: [Fa.FaSitemap, "#2563EB"],
    brain:   [Fa.FaBrain, "#7C3AED"],
    db:      [Fa.FaDatabase, "#0D9488"],
    bolt:    [Fa.FaBolt, "#F59E0B"],
    chart:   [Fa.FaChartLine, "#0D9488"],
    check:   [Fa.FaCheckCircle, "#0D9488"],
    cloud:   [Fa.FaCloud, "#2563EB"],
    route:   [Fa.FaRoute, "#F59E0B"],
    sync:    [Fa.FaSyncAlt, "#7C3AED"],
    cog:     [Fa.FaCog, "#64748B"],
    rocket:  [Fa.FaRocket, "#E11D48"],
    bulb:    [Fa.FaLightbulb, "#F59E0B"],
    arrow:   [Fa.FaArrowRight, "#94A3B8"],
    ban:     [Fa.FaBan, "#E11D48"],
    eye:     [Fa.FaEye, "#2563EB"],
    play:    [Fa.FaPlayCircle, "#E11D48"],
    plug:    [Fa.FaPlug, "#0D9488"],
    users:   [Fa.FaUsers, "#2563EB"],
    // white variants for dark slides / chips
    robotW:  [Fa.FaRobot, "#FFFFFF"],
    boltW:   [Fa.FaBolt, "#FFFFFF"],
    playW:   [Fa.FaPlayCircle, "#FFFFFF"],
    checkW:  [Fa.FaCheckCircle, "#FFFFFF"],
    // business-case deck extras
    warn:    [Fa.FaExclamationTriangle, "#E11D48"],
    warnA:   [Fa.FaExclamationTriangle, "#F59E0B"],
    phone:   [Fa.FaPhoneAlt, "#64748B"],
    dollar:  [Fa.FaMoneyBillWave, "#E11D48"],
    dollarG: [Fa.FaMoneyBillWave, "#16A34A"],
    clock:   [Fa.FaHourglassHalf, "#E11D48"],
    down:    [Fa.FaArrowDown, "#E11D48"],
    up:      [Fa.FaArrowUp, "#16A34A"],
    flag:    [Fa.FaFlagCheckered, "#2563EB"],
    times:   [Fa.FaTimesCircle, "#E11D48"],
    wrench:  [Fa.FaWrench, "#7C3AED"],
    server:  [Fa.FaServer, "#64748B"],
    list:    [Fa.FaListUl, "#2563EB"],
    smile:   [Fa.FaSmile, "#16A34A"],
    frown:   [Fa.FaFrown, "#E11D48"],
    target:  [Fa.FaBullseye, "#7C3AED"],
    chartB:  [Fa.FaChartBar, "#0D9488"],
  };
  fs.mkdirSync("icons", { recursive: true });
  for (const [name, [comp, color]] of Object.entries(icons)) {
    await iconPng(comp, color, `icons/${name}.png`);
    // also a WHITE variant (`<name>W`) for placing on saturated colored chips
    if (!name.endsWith("W")) await iconPng(comp, "#FFFFFF", `icons/${name}W.png`);
  }
  console.log("ASSETS OK");
})();
