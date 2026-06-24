"use client";

import { useCallback, useEffect, useState } from "react";
import type { PostItem } from "@/lib/types";
import { PostCard } from "./PostCard";

const POLL_INTERVAL_MS = 2_000;
const LIMIT = 40;

export function LivePostsFeed() {
  const [posts, setPosts] = useState<PostItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const resp = await fetch(`/api/posts/recent?limit=${LIMIT}`, { cache: "no-store" });
      if (!resp.ok) throw new Error(`API returned ${resp.status}`);
      const data = await resp.json();
      setPosts(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load posts");
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  return (
    <div>
      <div className="header-row">
        <div>
          <h2 style={{ margin: 0 }}>
            <span className="live-dot" style={{ marginRight: 8 }} />
            Live posts
          </h2>
          <span className="muted">streaming from the Bluesky firehose &middot; refreshes every 2s</span>
        </div>
      </div>
      {error && <p className="muted">{error}</p>}
      {posts.length === 0 && !error && <p className="muted">Waiting for posts&hellip;</p>}
      <div className="post-feed">
        {posts.map((post) => (
          <PostCard key={post.id} post={post} />
        ))}
      </div>
    </div>
  );
}
