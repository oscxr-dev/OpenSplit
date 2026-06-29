/**
 * Coarse country-centroid lookup for the Public Teams map.
 *
 * Privacy: country/city-level approximation ONLY — we never store or use precise
 * coordinates. A team with no (or unknown) country is grouped under "Unknown
 * location" and simply isn't plotted, which never breaks the map.
 */

// [longitude, latitude] approximate country centroids (extend as needed).
const COUNTRY_CENTROIDS: Record<string, [number, number]> = {
  argentina: [-64, -34],
  australia: [134, -25],
  austria: [14.5, 47.5],
  belgium: [4.5, 50.8],
  brazil: [-51, -10],
  canada: [-106, 56],
  chile: [-71, -30],
  china: [104, 35],
  colombia: [-74, 4],
  'czechia': [15.5, 49.8],
  'czech republic': [15.5, 49.8],
  denmark: [10, 56],
  'el salvador': [-88.9, 13.8],
  finland: [26, 64],
  france: [2.2, 46.2],
  germany: [10.4, 51.2],
  greece: [22, 39],
  india: [78, 22],
  indonesia: [113, -0.8],
  ireland: [-8, 53.4],
  italy: [12.6, 42.8],
  japan: [138, 36],
  mexico: [-102, 23.6],
  netherlands: [5.3, 52.1],
  'new zealand': [172, -41],
  nigeria: [8, 9],
  norway: [9, 61],
  poland: [19, 52],
  portugal: [-8, 39.5],
  romania: [25, 46],
  russia: [97, 62],
  'south africa': [24, -29],
  'south korea': [128, 36],
  spain: [-3.7, 40.2],
  sweden: [16, 62],
  switzerland: [8.2, 46.8],
  turkey: [35, 39],
  ukraine: [31, 49],
  'united kingdom': [-2, 54],
  uk: [-2, 54],
  'united states': [-98, 39.5],
  usa: [-98, 39.5],
  'united states of america': [-98, 39.5],
  us: [-98, 39.5],
};

/** Returns [lon, lat] for a country name, or null if unknown. */
export function countryCoordinates(country: string | null | undefined): [number, number] | null {
  if (!country) return null;
  return COUNTRY_CENTROIDS[country.trim().toLowerCase()] ?? null;
}
