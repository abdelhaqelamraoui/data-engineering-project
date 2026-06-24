import type { PostItem } from "@/lib/types";
import { formatRelativeTime, shortenDid } from "@/lib/format";

export function BeforeAfterCard({ post }: { post: PostItem }) {
  const hasTerms = post.hashtags.length > 0 || post.words.length > 0;

  return (
    <article className="post-card">
      <div className="post-card-header">
        <span className="post-author">{shortenDid(post.did)}</span>
        <div className="post-meta">
          {post.lang && <span className="badge">{post.lang}</span>}
          <span className="muted">{formatRelativeTime(post.received_at)}</span>
        </div>
      </div>

      <div className="before-after">
        <div className="ba-col before">
          <span className="ba-label">Before · raw text</span>
          <p className="post-text">{post.text}</p>
        </div>
        <div className="ba-col after">
          <span className="ba-label">After · cleaned + extracted terms</span>
          <p className="cleaned-text">{post.cleaned_text || <span className="empty-hint">(nothing left after cleaning)</span>}</p>
          {hasTerms ? (
            <div className="term-chips">
              {post.hashtags.map((tag) => (
                <span key={tag} className="term-chip is-hashtag">{tag}</span>
              ))}
              {post.words.map((word) => (
                <span key={word} className="term-chip">{word}</span>
              ))}
            </div>
          ) : (
            <p className="empty-hint">no terms extracted (too short, stopwords, or filtered out)</p>
          )}
        </div>
      </div>
    </article>
  );
}
