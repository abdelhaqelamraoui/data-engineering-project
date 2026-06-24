import Link from "next/link";
import { Sparkline } from "@/components/Sparkline";
import { formatBucket } from "@/lib/format";
import type { TermHistoryResponse } from "@/lib/types";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:8000";

async function fetchHistory(term: string): Promise<TermHistoryResponse> {
  const resp = await fetch(
    `${API_INTERNAL_URL}/trending/history?term=${encodeURIComponent(term)}`,
    { cache: "no-store" },
  );
  if (!resp.ok) throw new Error(`API returned ${resp.status}`);
  return resp.json();
}

export default async function TermPage({ params }: { params: { term: string } }) {
  const term = decodeURIComponent(params.term);
  const history = await fetchHistory(term);

  return (
    <main className="container">
      <p><Link href="/">&larr; back to trending</Link></p>
      <h1>{term}</h1>
      <div className="panel">
        <h3 style={{ marginTop: 0 }}>Activity over time</h3>
        <Sparkline values={history.points.map((p) => p.count)} width={600} height={120} />
        {history.points.length > 0 && (
          <table style={{ marginTop: 16 }}>
            <thead>
              <tr>
                <th>Bucket</th>
                <th>Count</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {[...history.points].reverse().map((point) => (
                <tr key={point.bucket}>
                  <td>{formatBucket(point.bucket)}</td>
                  <td>{point.count}</td>
                  <td className="score">{point.score.toFixed(2)}×</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
