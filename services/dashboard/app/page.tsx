import { TrendingBoard } from "@/components/TrendingBoard";

export default function HomePage() {
  return (
    <main className="container">
      <h1>Trending Topics</h1>
      <p className="muted">Spiking hashtags and keywords from the Bluesky firehose, ranked by acceleration.</p>
      <TrendingBoard />
    </main>
  );
}
