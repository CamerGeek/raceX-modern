import { ImageResponse } from "next/og";

export const alt = "RaceX — Analyse des courses hippiques";
export const size = {
  width: 1200,
  height: 630,
};
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          alignItems: "center",
          background: "linear-gradient(135deg, #103b32 0%, #1d594b 62%, #c96f3b 150%)",
          color: "#fbfaf5",
          display: "flex",
          flexDirection: "column",
          height: "100%",
          justifyContent: "center",
          padding: "72px",
          width: "100%",
        }}
      >
        <div style={{ color: "#f2b84b", fontSize: 24, fontWeight: 700, letterSpacing: 12 }}>
          COURSES · ANALYSES · PRONOSTICS
        </div>
        <div style={{ fontSize: 112, fontWeight: 800, letterSpacing: -7, marginTop: 32 }}>
          RaceX
        </div>
        <div style={{ color: "#e8eee5", fontSize: 35, marginTop: 20 }}>
          L’analyse hippique, au rythme des courses.
        </div>
        <div style={{ background: "#c96f3b", height: 6, marginTop: 48, width: 160 }} />
      </div>
    ),
    { ...size },
  );
}
