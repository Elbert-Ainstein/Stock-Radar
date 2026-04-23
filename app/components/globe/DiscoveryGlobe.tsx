"use client";

import React, { useState, useEffect, useCallback } from "react";
import type { GlobeCandidate } from "./geo-data";
import { useGlobeRefs, useGlobeScene } from "./useGlobeScene";
import { usePins } from "./usePins";
import GlobeTooltip from "./GlobeTooltip";
import GlobeCard from "./GlobeCard";

export type { GlobeCandidate };

export default function DiscoveryGlobe({
  candidates,
}: {
  candidates: GlobeCandidate[];
}) {
  const refs = useGlobeRefs();
  const [selectedCandidate, setSelectedCandidate] = useState<GlobeCandidate | null>(null);
  const [tooltipData, setTooltipData] = useState<{
    candidate: GlobeCandidate;
    x: number;
    y: number;
  } | null>(null);

  const onHover = useCallback(
    (data: { candidate: GlobeCandidate; x: number; y: number } | null) => {
      setTooltipData(data);
    },
    []
  );

  const onSelect = useCallback((candidate: GlobeCandidate) => {
    setSelectedCandidate(candidate);
  }, []);

  useGlobeScene(refs, { onHover, onSelect });

  const { geoLocated, unmappedCount, fetchingLocations } = usePins(
    candidates,
    refs.pinsGroupRef
  );

  // Close card on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedCandidate(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="relative">
      {/* Globe canvas */}
      <div
        ref={refs.containerRef}
        className="w-full rounded-xl overflow-hidden"
        style={{
          height: "520px",
          background: "radial-gradient(ellipse at center, #0a0a1a 0%, #000 70%)",
          cursor: "grab",
        }}
      />

      {/* Stats overlay */}
      <div className="absolute top-4 left-4 flex flex-col gap-1">
        <div className="text-xs font-medium text-white/70">
          {fetchingLocations ? (
            <span className="text-amber-400/80">Fetching company locations...</span>
          ) : (
            <>
              {geoLocated.length} companies mapped
              {unmappedCount > 0 && (
                <span className="text-white/40"> · {unmappedCount} unmapped</span>
              )}
            </>
          )}
        </div>
        <div className="text-[10px] text-white/40">
          Drag to rotate · Click a pin for details
        </div>
      </div>

      {/* Legend */}
      <div className="absolute top-4 right-4 flex items-center gap-3 text-[10px] text-white/50">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-400" /> Score {"\u2265"} 8
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-amber-400" /> Score 5–7
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-rose-400" /> Score &lt; 5
        </span>
      </div>

      {/* Hover tooltip */}
      {tooltipData && (
        <GlobeTooltip
          candidate={tooltipData.candidate}
          x={tooltipData.x}
          y={tooltipData.y}
        />
      )}

      {/* Selected candidate card */}
      {selectedCandidate && (
        <GlobeCard
          candidate={selectedCandidate}
          onClose={() => setSelectedCandidate(null)}
        />
      )}
    </div>
  );
}
