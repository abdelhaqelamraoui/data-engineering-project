export function formatBucket(bucket: string): string {
  if (!/^\d{12}$/.test(bucket)) return bucket;
  const year = bucket.slice(0, 4);
  const month = bucket.slice(4, 6);
  const day = bucket.slice(6, 8);
  const hour = bucket.slice(8, 10);
  const minute = bucket.slice(10, 12);
  return `${year}-${month}-${day} ${hour}:${minute} UTC`;
}

export function dateToBucket(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}` +
    `${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}`
  );
}

export function formatRelativeTime(isoString: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(isoString).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export function shortenDid(did: string): string {
  const id = did.replace(/^did:plc:/, "");
  return id.length > 12 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id;
}
