import { NextRequest, NextResponse } from "next/server";

const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:8000";

export async function GET(request: NextRequest) {
  const search = request.nextUrl.search;
  const resp = await fetch(`${API_INTERNAL_URL}/posts/recent${search}`, { cache: "no-store" });
  const body = await resp.text();
  return new NextResponse(body, {
    status: resp.status,
    headers: { "Content-Type": "application/json" },
  });
}
