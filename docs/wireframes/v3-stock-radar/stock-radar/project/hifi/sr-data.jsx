/* hifi/sr-data.jsx — fixture data shared across views */

const SR_TICKERS = [
  { ticker: 'NVDA', name: 'NVIDIA Corp',          price: 822.41, chg: +14.02, chgPct: +1.74, conv: 'strong', thesis: 1180, dcf: 920,  setup: 'AI capex',     last: '12m ago',  spark: [780,790,795,810,802,815,820,822], notes: 7, scouts: 9 },
  { ticker: 'CRWD', name: 'CrowdStrike Holdings', price: 122.40, chg: -3.18,  chgPct: -2.53, conv: 'strong', thesis: 220,  dcf: 165,  setup: 'Q3 catalyst', last: '4h ago',   spark: [128,131,127,124,126,123,124,122], notes: 12, scouts: 7 },
  { ticker: 'META', name: 'Meta Platforms',       price: 482.15, chg: +5.40,  chgPct: +1.13, conv: 'good',   thesis: 620,  dcf: 540,  setup: 'Reels mon.',   last: '1d ago',   spark: [470,468,475,478,480,476,479,482], notes: 4, scouts: 6 },
  { ticker: 'SHOP', name: 'Shopify Inc',          price:  68.92, chg: +0.84,  chgPct: +1.23, conv: 'good',   thesis:  92,  dcf:  74,  setup: 'GMV beat',     last: '2h ago',   spark: [62,64,66,65,67,67,68,68], notes: 3, scouts: 5 },
  { ticker: 'AMD',  name: 'Advanced Micro',       price: 158.73, chg: -2.10,  chgPct: -1.31, conv: 'watch',  thesis: 195,  dcf: 175,  setup: 'MI300 ramp',   last: '6h ago',   spark: [165,164,162,160,161,159,160,158], notes: 5, scouts: 4 },
  { ticker: 'TSLA', name: 'Tesla Inc',            price: 245.18, chg: +0.12,  chgPct: +0.05, conv: 'watch',  thesis: 320,  dcf: 285,  setup: 'Robotaxi',     last: '8h ago',   spark: [240,243,247,244,246,245,245,245], notes: 9, scouts: 8 },
  { ticker: 'SNOW', name: 'Snowflake Inc',        price: 138.55, chg: -1.92,  chgPct: -1.37, conv: 'fade',   thesis: 165,  dcf: 195,  setup: 'Margin comp.',  last: '3d ago',   spark: [148,146,142,140,142,139,140,138], notes: 6, scouts: 3 },
  { ticker: 'ROKU', name: 'Roku Inc',             price:  62.41, chg: -1.08,  chgPct: -1.70, conv: 'fade',   thesis:  78,  dcf:  85,  setup: 'CTV slow',     last: '2d ago',   spark: [68,67,65,64,65,63,63,62], notes: 2, scouts: 2 },
  { ticker: 'PLTR', name: 'Palantir Tech',        price:  24.18, chg: +0.42,  chgPct: +1.77, conv: 'watch',  thesis:  32,  dcf:  19,  setup: 'AIP traction', last: '5h ago',   spark: [22,22,23,23,24,23,24,24], notes: 8, scouts: 6 },
  { ticker: 'NFLX', name: 'Netflix Inc',          price: 612.30, chg: +8.20,  chgPct: +1.36, conv: 'good',   thesis: 740,  dcf: 660,  setup: 'Ad tier',      last: '1d ago',   spark: [598,601,604,608,605,610,611,612], notes: 4, scouts: 5 },
  { ticker: 'PYPL', name: 'PayPal Holdings',      price:  61.24, chg: -0.95,  chgPct: -1.53, conv: 'broken', thesis:  72,  dcf:  68,  setup: 'Take-rate',     last: '12d ago',  spark: [68,66,65,64,63,62,62,61], notes: 1, scouts: 1 },
  { ticker: 'ENPH', name: 'Enphase Energy',       price:  98.40, chg: -2.84,  chgPct: -2.81, conv: 'broken', thesis: 145,  dcf: 105,  setup: 'Solar reset',   last: '8d ago',   spark: [110,108,105,102,101,100,99,98], notes: 0, scouts: 1 },
];

window.SR_TICKERS = SR_TICKERS;
