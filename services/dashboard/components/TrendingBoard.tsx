"use client";

import { useCallback, useEffect, useState } from "react";
import type { TrendingResponse } from "@/lib/types";
import { formatBucket } from "@/lib/format";
import { TrendList } from "./TrendList";
import { TimeSelector } from "./TimeSelector";

const POLL_INTERVAL_MS = 30_000;

export function TrendingBoard() {
  const [bucket, setBucket] = useState<string | null>(null);
  const [data, setData] = useState<TrendingResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isLive = bucket === null;

  const load = useCallback(async (atBucket: string | null) => {
    try {
      const query = atBucket ? `?at=${atBucket}&limit=20` : "?limit=20";
      const resp = await fetch(`/api/trending${query}`, { cache: "no-store" });
      if (!resp.ok) throw new Error(`API returned ${resp.status}`);
      setData(await resp.json());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load trends");
    }
  }, []);

  useEffect(() => {
    load(bucket);
    if (!isLive) return;
    const interval = setInterval(() => load(bucket), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [bucket, isLive, load]);

  return (
    <div className="panel">
      <div className="header-row">
        <div>
          <h2 style={{ margin: 0 }}>{isLive ? "Trending now" : "Trending at"}</h2>
          <span className="muted">
            {data?.bucket ? formatBucket(data.bucket) : "waiting for data..."}
            {isLive && " · refreshes every 30s"}
          </span>
        </div>
        <TimeSelector isLive={isLive} onSelectBucket={setBucket} onGoLive={() => setBucket(null)} />
      </div>
      {error && <p className="muted">{error}</p>}
      {data && <TrendList items={data.items} />}
    </div>
  );
}
