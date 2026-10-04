/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo } from "react";
import { sankey, sankeyLinkHorizontal } from "d3-sankey";
import { type Demo, fuelColor } from "./data";

const ORIGIN: Record<string, string> = {
  vlsfo: "Crude oil", lng: "Fossil gas", meoh: "Fossil gas", nh3: "Fossil gas",
  biolng: "Waste biomass", emeoh: "Renewable power", gnh3: "Renewable power", h2: "Renewable power",
};
const ORIGIN_COLOR: Record<string, string> = { "Crude oil": "#8a7a6a", "Fossil gas": "#7f8fa6", "Waste biomass": "#8fb36a", "Renewable power": "#5fc4e8" };

export function Sankey({ d, width, height, highlight, reveal }: { d: Demo; width: number; height: number; highlight: string | null; reveal: number }) {
  const graph = useMemo(() => {
    const origins = [...new Set(Object.values(ORIGIN))];
    const nodes: any[] = [
      ...origins.map((o) => ({ id: o, color: ORIGIN_COLOR[o] })),
      ...d.fuels.map((f: any) => ({ id: f.key, name: f.name, color: f.color })),
      { id: "wtt", name: "Making the fuel (well-to-tank)", color: "#c9a14a" },
      { id: "ttw", name: "Burning the fuel (tank-to-wake)", color: "#d9705f" },
    ];
    const idx = new Map(nodes.map((n, i) => [n.id, i]));
    const links: any[] = [];
    for (const f of d.fuels) {
      links.push({ source: idx.get(ORIGIN[f.key]), target: idx.get(f.key), value: Math.max(f.wtw, 2), fuel: f.key });
      links.push({ source: idx.get(f.key), target: idx.get("wtt"), value: Math.max(f.wtt, 1), fuel: f.key });
      links.push({ source: idx.get(f.key), target: idx.get("ttw"), value: Math.max(f.ttw, 1), fuel: f.key });
    }
    return sankey<any, any>().nodeWidth(16).nodePadding(16).extent([[150, 10], [width - 250, height - 10]])({ nodes: nodes.map((n) => ({ ...n })), links });
  }, [d, width, height]);
  const path = sankeyLinkHorizontal();
  return (
    <svg width={width} height={height} role="img" aria-label="Fuel life-cycle emissions">
      <g style={{ clipPath: `inset(0 ${(1 - reveal) * 100}% 0 0)` } as any}>
        {graph.links.map((l: any, i: number) => (
          <path key={i} d={path(l) ?? ""} fill="none" stroke={fuelColor(d, l.fuel)} strokeWidth={Math.max(1, l.width)}
            strokeOpacity={highlight ? (l.fuel === highlight ? 0.85 : 0.08) : 0.42} />
        ))}
        {graph.nodes.map((n: any) => (
          <g key={n.id}>
            <rect x={n.x0} y={n.y0} width={n.x1 - n.x0} height={Math.max(2, n.y1 - n.y0)} fill={n.color} />
            <text x={n.x0 < width / 3 ? n.x0 - 8 : n.x1 + 8} y={(n.y0 + n.y1) / 2} dy="0.35em" fontSize="16"
              fill={highlight && n.id === highlight ? "#ff5d5d" : "#e8eef2"} fontWeight={highlight && n.id === highlight ? 700 : 500}
              textAnchor={n.x0 < width / 3 ? "end" : "start"}>
              {n.name ?? n.id}{n.id === "wtt" || n.id === "ttw" ? "" : ""}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}
