export type Horse = Record<string, string | number | boolean | null>;

export type QuinteAnalysis = {
  race_type: "flat" | "trot";
  row_count: number;
  rows: Horse[];
};

export const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function parisDate() {
  return new Intl.DateTimeFormat("fr-CA", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export const TOP_EIGHT_REVALIDATE_SECONDS = 60;
const TOP_EIGHT_TIMEOUT_MS = 8000;

export async function fetchPublicTopEight(): Promise<QuinteAnalysis | null> {
  try {
    const response = await fetch(
      `${apiUrl}/api/v1/races/turfomania/quinte/today/public?date=${parisDate()}`,
      {
        next: { revalidate: TOP_EIGHT_REVALIDATE_SECONDS },
        signal: AbortSignal.timeout(TOP_EIGHT_TIMEOUT_MS),
      },
    );
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as QuinteAnalysis;
  } catch {
    return null;
  }
}
