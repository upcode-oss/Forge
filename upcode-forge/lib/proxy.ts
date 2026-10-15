import { NextRequest } from "next/server";

export async function proxy(request: NextRequest) {
  const backend = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const url = new URL(
    request.nextUrl.pathname + request.nextUrl.search,
    backend,
  );
  const headers = new Headers(request.headers);
  for (const name of [
    "host",
    "connection",
    "transfer-encoding",
    "content-length",
    "accept-encoding",
  ])
    headers.delete(name);
  try {
    const response = await fetch(url, {
      method: request.method,
      headers,
      redirect: "manual",
      cache: "no-store",
      ...(request.method === "GET" || request.method === "HEAD"
        ? {}
        : { body: request.body, duplex: "half" }),
      signal: request.signal,
    } as RequestInit);
    const outgoing = new Headers(response.headers);
    for (const name of [
      "content-encoding",
      "content-length",
      "connection",
      "transfer-encoding",
    ])
      outgoing.delete(name);
    return new Response(response.body, {
      status: response.status,
      headers: outgoing,
    });
  } catch {
    return Response.json(
      { detail: "Forge backend is unavailable. Check the backend service." },
      { status: 502 },
    );
  }
}
