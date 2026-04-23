import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import type { GlobeCandidate } from "./geo-data";
import { geocodeCandidate } from "./geo-data";
import { latLngToVector3, scoreColor } from "./globe-helpers";
import { GLOBE_RADIUS } from "./useGlobeScene";

export interface GeoLocatedCandidate {
  candidate: GlobeCandidate;
  lat: number;
  lng: number;
}

export function usePins(
  candidates: GlobeCandidate[],
  pinsGroupRef: React.MutableRefObject<THREE.Group | null>
) {
  // Enriched location data fetched from API for candidates missing hq fields
  const [enrichedLocations, setEnrichedLocations] = useState<
    Record<string, { city: string; state: string; country: string }>
  >({});
  const [fetchingLocations, setFetchingLocations] = useState(false);

  // Fetch missing locations from API on mount
  useEffect(() => {
    const unmapped = candidates.filter(
      (c) => !c.hq_city && !c.hq_state && !c.hq_country
    );
    if (unmapped.length === 0 || fetchingLocations) return;

    const tickers = unmapped.map((c) => c.ticker);
    const needed = tickers.filter((t) => !enrichedLocations[t]);
    if (needed.length === 0) return;

    setFetchingLocations(true);
    fetch("/api/locations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers: needed }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.locations) {
          setEnrichedLocations((prev) => ({ ...prev, ...data.locations }));
        }
      })
      .catch(() => {})
      .finally(() => setFetchingLocations(false));
  }, [candidates]); // eslint-disable-line react-hooks/exhaustive-deps

  // Geocoded candidates with coordinates
  const geoLocated = useMemo(() => {
    return candidates
      .map((c) => {
        const enriched = enrichedLocations[c.ticker];
        const candidate: GlobeCandidate = enriched
          ? {
              ...c,
              hq_city: c.hq_city || enriched.city,
              hq_state: c.hq_state || enriched.state,
              hq_country: c.hq_country || enriched.country,
            }
          : c;
        const coords = geocodeCandidate(candidate);
        return coords
          ? { candidate, lat: coords[0], lng: coords[1] }
          : null;
      })
      .filter(Boolean) as GeoLocatedCandidate[];
  }, [candidates, enrichedLocations]);

  const unmappedCount = candidates.length - geoLocated.length;

  // Update pins when candidates change
  useEffect(() => {
    const pinsGroup = pinsGroupRef.current;
    if (!pinsGroup) return;

    // Clear existing pins
    while (pinsGroup.children.length > 0) {
      const child = pinsGroup.children[0];
      pinsGroup.remove(child);
      if (child instanceof THREE.Mesh) {
        child.geometry.dispose();
        (child.material as THREE.Material).dispose();
      }
    }

    geoLocated.forEach((item, i) => {
      const { candidate, lat, lng } = item;
      const pos = latLngToVector3(lat, lng, GLOBE_RADIUS);

      // Pin dot
      const color = scoreColor(candidate.quant_score);
      const pinSize = Math.max(0.02, Math.min(0.045, candidate.market_cap_b / 200));
      const pinGeom = new THREE.SphereGeometry(pinSize, 12, 12);
      const pinMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(color),
        transparent: true,
        opacity: 0.95,
      });
      const pin = new THREE.Mesh(pinGeom, pinMat);
      pin.position.copy(pos);
      pin.userData = { isPin: true, candidate };
      pinsGroup.add(pin);

      // Pulse ring
      const pulseGeom = new THREE.RingGeometry(pinSize * 1.5, pinSize * 2.2, 24);
      const pulseMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(color),
        transparent: true,
        opacity: 0.3,
        side: THREE.DoubleSide,
      });
      const pulse = new THREE.Mesh(pulseGeom, pulseMat);
      pulse.position.copy(pos);
      pulse.lookAt(pos.clone().multiplyScalar(2));
      pulse.userData = { isPulse: true, phase: i * 0.7 };
      pinsGroup.add(pulse);

      // Vertical beam (for high-score candidates)
      if (candidate.quant_score >= 7) {
        const beamHeight = 0.08 + candidate.quant_score * 0.008;
        const beamGeom = new THREE.CylinderGeometry(0.003, 0.003, beamHeight, 6);
        const beamMat = new THREE.MeshBasicMaterial({
          color: new THREE.Color(color),
          transparent: true,
          opacity: 0.5,
        });
        const beam = new THREE.Mesh(beamGeom, beamMat);

        const direction = pos.clone().normalize();
        beam.position.copy(pos).add(direction.multiplyScalar(beamHeight / 2));
        beam.lookAt(new THREE.Vector3(0, 0, 0));
        beam.rotateX(Math.PI / 2);

        pinsGroup.add(beam);
      }
    });
  }, [geoLocated, pinsGroupRef]);

  return { geoLocated, unmappedCount, fetchingLocations };
}
