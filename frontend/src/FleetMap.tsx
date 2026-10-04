/* eslint-disable @typescript-eslint/no-explicit-any */
import { useMemo } from "react";
import DeckGL from "@deck.gl/react";
import { PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { Map } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import { type Demo, type Plan, fuelColor, shipPos } from "./data";

const STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json";

const hex = (h: string, a = 255): [number, number, number, number] =>
  [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16), a];

function recolor(e: any) {
  const map = e.target;
  for (const l of map.getStyle().layers) {
    if (l.type === "background") map.setPaintProperty(l.id, "background-color", "#16334f");
    else if (l.id.includes("water")) {
      if (l.type === "fill") map.setPaintProperty(l.id, "fill-color", "#0b2238");
      if (l.type === "line") map.setPaintProperty(l.id, "line-color", "#0b2238");
    } else if (l.type === "fill") map.setPaintProperty(l.id, "fill-color", "#173958");
    else if (l.type === "line" && l.id.includes("boundary")) map.setPaintProperty(l.id, "line-color", "#2c5476");
    else if (l.type === "line") map.setLayoutProperty(l.id, "visibility", "none");
  }
  (window as any).__mapReady = ((window as any).__mapReady || 0) + 1;
}

export type MapProps = {
  d: Demo; plan: Plan; hours: number; mode: "bau" | "opt";
  view?: { longitude: number; latitude: number; zoom: number };
  flagBad?: number;            // 0..1 pulse strength for D/E ships
  storm?: { center: [number, number]; radius: number; spin: number; routes: string[]; alpha: number };
  hideShips?: boolean;
};

export default function FleetMap({ d, plan, hours, mode, view, flagBad = 0, storm, hideShips }: MapProps) {
  const vs = view ?? { longitude: 82.5, latitude: 11.5, zoom: 3.55 };
  const ports = useMemo(() => {
    const out: any[] = [{ name: "Chennai", pos: d.routes[0].path[0], hub: true }];
    for (const r of d.routes) out.push({ name: r.dest, pos: r.path[r.path.length - 1] });
    return out;
  }, [d]);

  const ships = useMemo(() => plan.vessels.filter((v) => v.route), [plan]);
  const nm = (key: string) => d.routes.find((r: any) => r.key === key).nm;

  const shipData = ships.map((v) => ({
    v, pos: shipPos(d, v.route!, nm(v.route!), v.speed_kn, v.id, hours),
    trail: [0, 2, 4, 6, 8, 10, 12].map((k) => shipPos(d, v.route!, nm(v.route!), v.speed_kn, v.id, hours - k * 1.6)),
    color: mode === "bau" ? (v.fuel === "lng" ? "#7aa7d9" : "#ffb547") : fuelColor(d, v.fuel),
  }));

  const stormRoutes = new Set(storm?.routes ?? []);
  const layers: any[] = [
    new PathLayer({
      id: "routes", data: d.routes, getPath: (r: any) => r.path, widthUnits: "pixels",
      getWidth: (r: any) => (stormRoutes.has(r.key) ? 3.5 : 2),
      getColor: (r: any) => (stormRoutes.has(r.key) ? hex("#ff5d5d", 60 + 180 * (storm?.alpha ?? 0)) : hex("#3fb8af", 110)),
      updateTriggers: { getColor: [storm?.alpha, storm?.routes?.join()], getWidth: [storm?.routes?.join()] },
    }),
  ];
  if (storm && storm.alpha > 0) {
    const arms = [0, 1, 2, 3].map((a) => {
      const pts: [number, number][] = [];
      for (let k = 0; k <= 40; k++) {
        const r = storm.radius * (k / 40);
        const ang = storm.spin + a * Math.PI / 2 + k * 0.13;
        pts.push([storm.center[0] + r * Math.cos(ang) / Math.cos(storm.center[1] * Math.PI / 180), storm.center[1] + r * Math.sin(ang)]);
      }
      return pts;
    });
    layers.push(new ScatterplotLayer({ id: "storm-core", data: [storm.center], getPosition: (p: any) => p, radiusUnits: "meters",
      getRadius: storm.radius * 111000, getFillColor: hex("#ff5d5d", 34 * storm.alpha), stroked: true, lineWidthUnits: "pixels",
      getLineWidth: 1.5, getLineColor: hex("#ff5d5d", 160 * storm.alpha), updateTriggers: { getFillColor: storm.alpha } }));
    layers.push(new PathLayer({ id: "storm-arms", data: arms, getPath: (p: any) => p, widthUnits: "pixels", getWidth: 3,
      getColor: hex("#ffd2d2", 200 * storm.alpha), capRounded: true, jointRounded: true }));
  }
  if (!hideShips) {
    layers.push(new PathLayer({ id: "trails", data: shipData, getPath: (s: any) => s.trail, widthUnits: "pixels", getWidth: 2.5,
      getColor: (s: any) => hex(s.color, 90), capRounded: true }));
    if (flagBad > 0) {
      layers.push(new ScatterplotLayer({ id: "bad", data: shipData.filter((s) => s.v.cii === "D" || s.v.cii === "E"),
        getPosition: (s: any) => s.pos, radiusUnits: "pixels", getRadius: 10 + 12 * flagBad, stroked: true, filled: false,
        lineWidthUnits: "pixels", getLineWidth: 2.5, getLineColor: hex("#ff5d5d", 255 * (1 - 0.6 * flagBad)),
        updateTriggers: { getRadius: flagBad, getLineColor: flagBad } }));
    }
    layers.push(new ScatterplotLayer({ id: "ships", data: shipData, getPosition: (s: any) => s.pos, radiusUnits: "pixels",
      getRadius: 6.5, getFillColor: (s: any) => hex(s.color), stroked: true, lineWidthUnits: "pixels", getLineWidth: 1.5,
      getLineColor: [11, 34, 56, 255] }));
  }
  layers.push(new ScatterplotLayer({ id: "ports", data: ports, getPosition: (p: any) => p.pos, radiusUnits: "pixels",
    getRadius: (p: any) => (p.hub ? 9 : 5), getFillColor: [232, 238, 242, 255], stroked: true, getLineColor: [63, 184, 175, 255],
    lineWidthUnits: "pixels", getLineWidth: 2 }));
  layers.push(new TextLayer({ id: "port-names", data: ports, getPosition: (p: any) => p.pos, getText: (p: any) => p.name,
    getSize: (p: any) => (p.hub ? 19 : 15), getColor: [232, 238, 242, 230], getPixelOffset: [0, -18], fontFamily: "Barlow, sans-serif",
    fontWeight: 600, outlineWidth: 3, outlineColor: [11, 34, 56, 255], fontSettings: { sdf: true } }));

  return (
    <DeckGL viewState={vs as any} controller={false} layers={layers} style={{ position: "absolute", inset: "0" }}>
      <Map mapStyle={STYLE} onLoad={recolor} attributionControl={false} />
    </DeckGL>
  );
}
