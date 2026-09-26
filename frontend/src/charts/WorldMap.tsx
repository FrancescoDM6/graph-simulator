import { useElementWidth } from "../hooks/useElementWidth";
import type { WorldInfo } from "../types";

interface Props {
  world: WorldInfo;
  occupationColors: Record<string, string>;
  siteColors: Record<string, string>; // site kind -> colour of the occupation that works it
  height?: number;
}

const PAD = 34; // room around the map for town names and sites

/** A world's map at a glance: towns (sized by their founding people, with a bar showing the
 * mix of occupations), the sites beside them (sized by capacity), and the roads. */
export function WorldMap({ world, occupationColors, siteColors, height = 190 }: Props) {
  const [ref, width] = useElementWidth<HTMLDivElement>();
  const at = new Map(
    world.towns.map((t) => [t.name, { x: PAD + t.position[0] * (width - 2 * PAD), y: PAD + t.position[1] * (height - 2 * PAD) }]),
  );
  return (
    <div className="world-map" ref={ref}>
      {width > 0 && (
        <svg width={width} height={height}>
          {world.roads.map((road) => {
            const a = at.get(road.from)!;
            const b = at.get(road.to)!;
            return <line key={`${road.from}-${road.to}`} className="map-road" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
          })}
          {world.towns.map((town) => {
            const { x, y } = at.get(town.name)!;
            const people = Object.values(town.founding).reduce((sum, n) => sum + n, 0);
            const half = 7 + 1.4 * Math.sqrt(people);
            let offset = -half;
            return (
              <g key={town.name}>
                <title>
                  {`${town.name}: ${Object.entries(town.founding)
                    .map(([o, n]) => `${n} ${o}s`)
                    .join(", ") || "nobody"}${town.sites.length ? `; ${town.sites.map((s) => `${s.kind} ×${s.scale.toFixed(2)}`).join(", ")}` : ""}`}
                </title>
                <rect className="map-town" x={x - half} y={y - half} width={2 * half} height={2 * half} rx={4} />
                <text className="map-count" x={x} y={y + 4} textAnchor="middle">
                  {people}
                </text>
                {/* the mix of occupations, as a bar along the bottom of the town */}
                {Object.entries(town.founding).map(([occupation, n]) => {
                  const w = (2 * half * n) / Math.max(1, people);
                  const segment = (
                    <rect key={occupation} x={x + offset} y={y + half - 4} width={w} height={4} fill={occupationColors[occupation] ?? "#999"} />
                  );
                  offset += w;
                  return segment;
                })}
                {town.sites.map((site, i) => {
                  const size = 4 + 4 * Math.min(2, site.scale);
                  const cx = x + half + 7 + size + i * (2 * size + 4);
                  return (
                    <rect
                      key={site.name}
                      className="map-site"
                      x={cx - size}
                      y={y - size}
                      width={2 * size}
                      height={2 * size}
                      transform={`rotate(45 ${cx} ${y})`}
                      stroke={siteColors[site.kind] ?? "#6b7280"}
                    />
                  );
                })}
                <text className="map-label" x={x} y={y + half + 13} textAnchor="middle">
                  {town.name}
                </text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}
