import * as THREE from "three";

export function latLngToVector3(lat: number, lng: number, radius: number): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lng + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -(radius * Math.sin(phi) * Math.cos(theta)),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta)
  );
}

export function scoreColor(score: number): string {
  if (score >= 8) return "#34d399";
  if (score >= 6.5) return "#4ade80";
  if (score >= 5) return "#fbbf24";
  if (score >= 3.5) return "#fb923c";
  return "#f87171";
}

export function signalLabel(signal: string): string {
  return signal === "bullish" ? "Bullish" : signal === "bearish" ? "Bearish" : "Neutral";
}

export function signalColor(signal: string): string {
  return signal === "bullish" ? "#34d399" : signal === "bearish" ? "#f87171" : "#94a3b8";
}
