export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    cache: "no-store",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Forge-Request": "1",
      ...options.headers,
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = Array.isArray(data.detail)
      ? data.detail
          .map(
            (v: { msg: string; loc: string[] }) =>
              `${v.loc.slice(1).join(".")}: ${v.msg}`,
          )
          .join("; ")
      : data.detail;
    throw new ApiError(
      response.status,
      typeof message === "string"
        ? message
        : "Request failed. Please try again.",
    );
  }
  return data as T;
}
export const json = (value: unknown) => JSON.stringify(value);
