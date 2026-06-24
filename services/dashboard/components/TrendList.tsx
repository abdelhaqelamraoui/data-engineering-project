import Link from "next/link";
import type { TrendingItem } from "@/lib/types";

export function TrendList({ items }: { items: TrendingItem[] }) {
  if (items.length === 0) {
    return <p className="muted">No trends for this time bucket yet.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Term</th>
          <th>Count</th>
          <th>Score</th>
          <th>Authors</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.rank}>
            <td><span className="rank-badge">{item.rank}</span></td>
            <td>
              <Link href={`/term/${encodeURIComponent(item.term)}`}>{item.term}</Link>
            </td>
            <td>{item.count}</td>
            <td className="score">{item.score.toFixed(2)}×</td>
            <td>{item.distinct_authors}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
