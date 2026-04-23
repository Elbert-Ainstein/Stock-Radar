// ─── Types ───
export interface GlobeCandidate {
  ticker: string;
  name: string;
  sector: string;
  industry?: string;
  price: number;
  change_pct: number;
  market_cap_b: number;
  revenue_growth_pct: number;
  quant_score: number;
  signal: string;
  stage: string;
  hq_city?: string;
  hq_state?: string;
  hq_country?: string;
  ai_confidence?: number | null;
  thesis?: string | null;
  tags?: string[];
  target_range?: { low?: number; base?: number; high?: number };
}

// ─── Known city geocoding database ───
// Covers the major financial/tech hubs where most public companies HQ
export const CITY_COORDS: Record<string, [number, number]> = {
  // US - Tech hubs
  "San Francisco, CA": [37.7749, -122.4194],
  "San Jose, CA": [37.3382, -121.8863],
  "Cupertino, CA": [37.323, -122.0322],
  "Mountain View, CA": [37.3861, -122.0839],
  "Palo Alto, CA": [37.4419, -122.143],
  "Sunnyvale, CA": [37.3688, -122.0363],
  "Santa Clara, CA": [37.3541, -121.9552],
  "Menlo Park, CA": [37.4529, -122.1817],
  "Redwood City, CA": [37.4852, -122.2364],
  "San Diego, CA": [32.7157, -117.1611],
  "Los Angeles, CA": [34.0522, -118.2437],
  "Irvine, CA": [33.6846, -117.8265],
  "Seattle, WA": [47.6062, -122.3321],
  "Redmond, WA": [47.674, -122.1215],
  "Austin, TX": [30.2672, -97.7431],
  "Dallas, TX": [32.7767, -96.797],
  "Houston, TX": [29.7604, -95.3698],
  "San Antonio, TX": [29.4241, -98.4936],
  "New York, NY": [40.7128, -74.006],
  "Boston, MA": [42.3601, -71.0589],
  "Cambridge, MA": [42.3736, -71.1097],
  "Chicago, IL": [41.8781, -87.6298],
  "Atlanta, GA": [33.749, -84.388],
  "Raleigh, NC": [35.7796, -78.6382],
  "Denver, CO": [39.7392, -104.9903],
  "Phoenix, AZ": [33.4484, -112.074],
  "Scottsdale, AZ": [33.4942, -111.9261],
  "Portland, OR": [45.5051, -122.675],
  "Salt Lake City, UT": [40.7608, -111.891],
  "Minneapolis, MN": [44.9778, -93.265],
  "Detroit, MI": [42.3314, -83.0458],
  "Philadelphia, PA": [39.9526, -75.1652],
  "Washington, DC": [38.9072, -77.0369],
  "Miami, FL": [25.7617, -80.1918],
  "Tampa, FL": [27.9506, -82.4572],
  "Charlotte, NC": [35.2271, -80.8431],
  "Nashville, TN": [36.1627, -86.7816],
  "Boise, ID": [43.615, -116.2023],
  "Milpitas, CA": [37.4323, -121.8996],
  "Fremont, CA": [37.5485, -121.9886],
  "Pleasanton, CA": [37.6604, -121.8758],
  "Wilmington, DE": [39.7391, -75.5398],
  "Omaha, NE": [41.2565, -95.9345],
  "St. Louis, MO": [38.627, -90.1994],
  "Indianapolis, IN": [39.7684, -86.1581],
  "Columbus, OH": [39.9612, -82.9988],
  "Pittsburgh, PA": [40.4406, -79.9959],
  "Chandler, AZ": [33.3062, -111.8413],

  // International
  "Amsterdam, Netherlands": [52.3676, 4.9041],
  "Veldhoven, Netherlands": [51.4201, 5.4052], // ASML
  "London, United Kingdom": [51.5074, -0.1278],
  "Paris, France": [48.8566, 2.3522],
  "Berlin, Germany": [52.52, 13.405],
  "Munich, Germany": [48.1351, 11.582],
  "Walldorf, Germany": [49.3063, 8.6428], // SAP
  "Dublin, Ireland": [53.3498, -6.2603],
  "Zurich, Switzerland": [47.3769, 8.5417],
  "Stockholm, Sweden": [59.3293, 18.0686],
  "Copenhagen, Denmark": [55.6761, 12.5683],
  "Helsinki, Finland": [60.1695, 24.9354],
  "Oslo, Norway": [59.9139, 10.7522],
  "Tokyo, Japan": [35.6762, 139.6503],
  "Seoul, South Korea": [37.5665, 126.978],
  "Taipei, Taiwan": [25.033, 121.5654],
  "Hsinchu, Taiwan": [24.8138, 120.9675], // TSMC
  "Beijing, China": [39.9042, 116.4074],
  "Shanghai, China": [31.2304, 121.4737],
  "Shenzhen, China": [22.5431, 114.0579],
  "Hangzhou, China": [30.2741, 120.1551],
  "Singapore, Singapore": [1.3521, 103.8198],
  "Bangalore, India": [12.9716, 77.5946],
  "Mumbai, India": [19.076, 72.8777],
  "Sydney, Australia": [-33.8688, 151.2093],
  "Melbourne, Australia": [-37.8136, 144.9631],
  "Toronto, Canada": [43.6532, -79.3832],
  "Vancouver, Canada": [49.2827, -123.1207],
  "Ottawa, Canada": [45.4215, -75.6972],
  "Montreal, Canada": [45.5017, -73.5673],
  "Tel Aviv, Israel": [32.0853, 34.7818],
  "Haifa, Israel": [32.7940, 34.9896],
  "São Paulo, Brazil": [-23.5505, -46.6333],
  "Mexico City, Mexico": [19.4326, -99.1332],
};

// State-level fallbacks for US
export const STATE_COORDS: Record<string, [number, number]> = {
  CA: [36.7783, -119.4179],
  TX: [31.9686, -99.9018],
  NY: [40.7128, -74.006],
  WA: [47.7511, -120.7401],
  MA: [42.4072, -71.3824],
  IL: [40.6331, -89.3985],
  GA: [33.749, -84.388],
  FL: [27.6648, -81.5158],
  CO: [39.5501, -105.7821],
  PA: [41.2033, -77.1945],
  NC: [35.7596, -79.0193],
  AZ: [34.0489, -111.0937],
  OR: [43.8041, -120.5542],
  UT: [39.321, -111.0937],
  MN: [46.7296, -94.6859],
  MI: [44.3148, -85.6024],
  OH: [40.4173, -82.9071],
  VA: [37.4316, -78.6569],
  NJ: [40.0583, -74.4057],
  CT: [41.6032, -73.0877],
  MD: [39.0458, -76.6413],
  TN: [35.5175, -86.5804],
  MO: [37.9643, -91.8318],
  IN: [40.2672, -86.1349],
  WI: [43.7844, -88.7879],
  NE: [41.4925, -99.9018],
  ID: [44.0682, -114.742],
  NV: [38.8026, -116.4194],
  DE: [38.9108, -75.5277],
};

// Country-level fallbacks
export const COUNTRY_COORDS: Record<string, [number, number]> = {
  "United States": [39.8283, -98.5795],
  "United Kingdom": [51.5074, -0.1278],
  Netherlands: [52.1326, 5.2913],
  Germany: [51.1657, 10.4515],
  France: [46.2276, 2.2137],
  Ireland: [53.1424, -7.6921],
  Switzerland: [46.8182, 8.2275],
  Sweden: [60.1282, 18.6435],
  Denmark: [56.2639, 9.5018],
  Finland: [61.9241, 25.7482],
  Norway: [60.472, 8.4689],
  Japan: [36.2048, 138.2529],
  "South Korea": [35.9078, 127.7669],
  Taiwan: [23.6978, 120.9605],
  China: [35.8617, 104.1954],
  India: [20.5937, 78.9629],
  Singapore: [1.3521, 103.8198],
  Australia: [-25.2744, 133.7751],
  Canada: [56.1304, -106.3468],
  Israel: [31.0461, 34.8516],
  Brazil: [-14.235, -51.9253],
  Mexico: [23.6345, -102.5528],
};

export function geocodeCandidate(c: GlobeCandidate): [number, number] | null {
  const city = c.hq_city || "";
  const state = c.hq_state || "";
  const country = c.hq_country || "";

  if (!city && !state && !country) return null;

  // Try city + state (US style)
  if (city && state) {
    const key1 = `${city}, ${state}`;
    if (CITY_COORDS[key1]) return CITY_COORDS[key1];
  }

  // Try city + country
  if (city && country) {
    const key2 = `${city}, ${country}`;
    if (CITY_COORDS[key2]) return CITY_COORDS[key2];
  }

  // Try US state fallback
  if (state && STATE_COORDS[state]) return STATE_COORDS[state];

  // Try country fallback
  if (country && COUNTRY_COORDS[country]) return COUNTRY_COORDS[country];

  // Last resort: try matching city name loosely
  for (const [key, coords] of Object.entries(CITY_COORDS)) {
    if (city && key.toLowerCase().startsWith(city.toLowerCase())) return coords;
  }

  return null;
}
