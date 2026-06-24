"use client";

import { useState } from "react";
import { dateToBucket } from "@/lib/format";

interface TimeSelectorProps {
  isLive: boolean;
  onSelectBucket: (bucket: string) => void;
  onGoLive: () => void;
}

export function TimeSelector({ isLive, onSelectBucket, onGoLive }: TimeSelectorProps) {
  const [value, setValue] = useState("");

  function handleView() {
    if (!value) return;
    // datetime-local has no timezone info, so the browser parses it as local
    // time - convert to the UTC bucket the API expects.
    onSelectBucket(dateToBucket(new Date(value)));
  }

  return (
    <div className="time-selector">
      <input
        type="datetime-local"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        step={60}
      />
      <button onClick={handleView}>View</button>
      {!isLive && <button className="secondary" onClick={onGoLive}>Back to live</button>}
    </div>
  );
}
