"use client";

import { useState } from "react";

export function usePipeline() {
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineMsg, setPipelineMsg] = useState<string | null>(null);

  const runPipeline = async (freeOnly = false) => {
    setPipelineRunning(true);
    setPipelineMsg("Starting pipeline...");
    try {
      const res = await fetch("/api/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ freeOnly }),
      });
      const data = await res.json();
      if (!data.success) {
        setPipelineMsg(data.message || "Failed to start");
        return;
      }
      setPipelineMsg("Pipeline running \u2014 this may take a few minutes...");
      // Poll until done, then reload
      const poll = setInterval(async () => {
        try {
          const status = await fetch("/api/pipeline");
          const s = await status.json();
          if (!s.running) {
            clearInterval(poll);
            setPipelineRunning(false);
            setPipelineMsg("Pipeline complete! Reloading...");
            setTimeout(() => window.location.reload(), 1000);
          }
        } catch {}
      }, 5000);
    } catch (e: any) {
      setPipelineMsg(`Error: ${e.message}`);
      setPipelineRunning(false);
    }
  };

  return { pipelineRunning, pipelineMsg, runPipeline };
}
