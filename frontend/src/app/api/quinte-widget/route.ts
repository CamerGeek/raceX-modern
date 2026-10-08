const widgetUrls = {
  starters: "https://www.zone-turf.fr/module/module_webmaster.php?e=partants",
  results: "https://www.zone-turf.fr/module/module_webmaster.php?e=rapport&f=quinte",
  liveResults: "https://www.zone-turf.fr/module/module_webmaster.php?e=rapport",
} as const;

export async function GET(request: Request) {
  const widgetType = new URL(request.url).searchParams.get("type") ?? "starters";
  let widgetUrl: string;
  if (widgetType === "starters") {
    widgetUrl = widgetUrls.starters;
  } else if (widgetType === "results") {
    widgetUrl = widgetUrls.results;
  } else if (widgetType === "live-results") {
    widgetUrl = widgetUrls.liveResults;
  } else {
    return new Response("Unknown Quinté+ widget type.", {
      status: 400,
      headers: { "Cache-Control": "no-store" },
    });
  }

  let upstream: Response;
  try {
    upstream = await fetch(widgetUrl, {
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
  } catch (error) {
    console.error("Unable to fetch the Zone-Turf Quinté+ widget.", error);
    return new Response("Unable to load the Zone-Turf widget.", {
      status: 502,
      headers: { "Cache-Control": "no-store" },
    });
  }

  if (!upstream.ok) {
    console.error(`Zone-Turf widget request failed with status ${upstream.status}.`);
    return new Response("Zone-Turf did not return the widget.", {
      status: 502,
      headers: { "Cache-Control": "no-store" },
    });
  }

  return new Response(await upstream.text(), {
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/javascript; charset=utf-8",
    },
  });
}
