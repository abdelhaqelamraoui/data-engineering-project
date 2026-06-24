import type { PostItem } from "@/lib/types";
import { formatRelativeTime, shortenDid } from "@/lib/format";

function renderTextWithHashtags(text: string) {
  return text.split(/(#\w+)/g).map((part, i) =>
    part.startsWith("#") ? (
      <span key={i} className="hashtag">{part}</span>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export function PostCard({ post }: { post: PostItem }) {
  return (
    <article className="post-card">
      <div className="post-card-header">
        <span className="post-author">{shortenDid(post.did)}</span>
        <div className="post-meta">
          {post.lang && <span className="badge">{post.lang}</span>}
          <span className="muted">{formatRelativeTime(post.received_at)}</span>
        </div>
      </div>
      <p className="post-text">{renderTextWithHashtags(post.text)}</p>
    </article>
  );
}
