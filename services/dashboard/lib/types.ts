export interface TrendingItem {
  rank: number;
  term: string;
  count: number;
  score: number;
  distinct_authors: number;
}

export interface TrendingResponse {
  bucket: string | null;
  items: TrendingItem[];
}

export interface HistoryPoint {
  bucket: string;
  count: number;
  score: number;
}

export interface TermHistoryResponse {
  term: string;
  points: HistoryPoint[];
}

export interface PostItem {
  id: string;
  did: string;
  text: string;
  timestamp: string | null;
  lang: string | null;
  received_at: string;
  // "after" preprocessing - see shared/preprocessing/
  cleaned_text: string;
  hashtags: string[];
  words: string[];
}

export interface RecentPostsResponse {
  items: PostItem[];
}
