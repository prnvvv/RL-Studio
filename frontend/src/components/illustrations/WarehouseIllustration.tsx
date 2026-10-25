/**
 * Static isometric warehouse illustration.
 *
 * This is a decorative product illustration, NOT a simulation renderer. It is
 * derived from no recorded environment state and must always be presented with
 * a visible "illustration preview" label. Real environment state must be
 * rendered by a data-bound viewer instead (see TODO T-902).
 *
 * All colours come from theme tokens, so the illustration follows both themes.
 */

const CELL = 34
const COS_30 = Math.cos(Math.PI / 6)
const Z_SCALE = 26

const GRID_W = 10
const GRID_D = 10

interface Point {
  x: number
  y: number
}

function project(x: number, y: number, z = 0): Point {
  return {
    x: (x - y) * CELL * COS_30 + 360,
    y: (x + y) * CELL * 0.5 - z * Z_SCALE + 104,
  }
}

function toPoints(points: Point[]): string {
  return points.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ')
}

interface Block {
  id: string
  x: number
  y: number
  w: number
  d: number
  h: number
  /** Stacked cartons drawn on top of the block. */
  cartons?: number
}

// Shelf rows and obstacle blocks. Static illustration layout, not recorded data.
const blocks: Block[] = [
  { id: 'shelf-a', x: 1, y: 1, w: 4, d: 1, h: 1.5, cartons: 3 },
  { id: 'shelf-b', x: 1, y: 3, w: 4, d: 1, h: 1.5, cartons: 2 },
  { id: 'shelf-c', x: 1, y: 5, w: 2, d: 1, h: 1.1, cartons: 1 },
  { id: 'shelf-d', x: 7, y: 1, w: 1, d: 4, h: 1.5, cartons: 2 },
  { id: 'obstacle-a', x: 3.2, y: 6.2, w: 2.4, d: 1, h: 0.9 },
  { id: 'obstacle-b', x: 8, y: 5, w: 1, d: 1, h: 1.2 },
]

const ROBOT = { x: 8.2, y: 8.2 }
const GOAL = { x: 2.4, y: 8.2 }

// Illustrative route, not a recorded trajectory.
const ROUTE = [
  { x: 8.2, y: 8.2 },
  { x: 8.2, y: 6.6 },
  { x: 6.6, y: 6.6 },
  { x: 6.6, y: 8.2 },
  { x: 2.4, y: 8.2 },
]

function depthOf(block: Block): number {
  return block.x + block.w / 2 + (block.y + block.d / 2)
}

const orderedBlocks = [...blocks].sort((a, b) => depthOf(a) - depthOf(b))

function BlockShape({ block }: { block: Block }) {
  const { x, y, w, d, h } = block
  const a = project(x, y, h)
  const b = project(x + w, y, h)
  const c = project(x + w, y + d, h)
  const dd = project(x, y + d, h)
  const b0 = project(x + w, y, 0)
  const c0 = project(x + w, y + d, 0)
  const d0 = project(x, y + d, 0)

  return (
    <g>
      {/* faces toward the viewer */}
      <polygon points={toPoints([b, c, c0, b0])} fill="var(--text-primary)" opacity={0.3} />
      <polygon points={toPoints([c, dd, d0, c0])} fill="var(--text-primary)" opacity={0.18} />
      <polygon points={toPoints([a, b, c, dd])} fill="var(--text-primary)" opacity={0.44} />
      <polygon
        points={toPoints([a, b, c, dd])}
        fill="none"
        stroke="var(--text-primary)"
        strokeOpacity={0.35}
        strokeWidth={1}
      />
      <polyline
        points={toPoints([b, b0])}
        fill="none"
        stroke="var(--text-primary)"
        strokeOpacity={0.28}
        strokeWidth={1}
        strokeDasharray="3 3"
      />
      {block.cartons
        ? Array.from({ length: block.cartons }, (_, index) => {
            const cartonCount = block.cartons ?? 1
            const inset = 0.18
            const cellWidth = (w - inset * 2) / Math.max(cartonCount, 1)
            const cx = x + inset + index * cellWidth
            const size = Math.min(0.5, cellWidth - 0.08)
            const top = h + 0.35
            const p1 = project(cx, y + 0.25, top)
            const p2 = project(cx + size, y + 0.25, top)
            const p3 = project(cx + size, y + 0.25 + size, top)
            const p4 = project(cx, y + 0.25 + size, top)
            const p3b = project(cx + size, y + 0.25 + size, h)
            const p4b = project(cx, y + 0.25 + size, h)
            return (
              <g key={`${block.id}-carton-${index}`}>
                <polygon
                  points={toPoints([p1, p2, p3, p4])}
                  fill="var(--text-primary)"
                  opacity={0.5}
                />
                <polygon
                  points={toPoints([p3, p4, p4b, p3b])}
                  fill="var(--text-primary)"
                  opacity={0.22}
                />
              </g>
            )
          })
        : null}
    </g>
  )
}

function floorGridLines(): Point[][] {
  const lines: Point[][] = []
  for (let i = 0; i <= GRID_W; i += 1) {
    lines.push([project(i, 0), project(i, GRID_D)])
  }
  for (let j = 0; j <= GRID_D; j += 1) {
    lines.push([project(0, j), project(GRID_W, j)])
  }
  return lines
}

export function WarehouseIllustration() {
  const floor = [project(0, 0), project(GRID_W, 0), project(GRID_W, GRID_D), project(0, GRID_D)]
  const goalTop = project(GOAL.x, GOAL.y, 0.05)
  const robotTop = project(ROBOT.x, ROBOT.y, 0.55)
  const routePath = ROUTE.map((p, index) => {
    const point = project(p.x, p.y, 0.05)
    return `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)},${point.y.toFixed(2)}`
  }).join(' ')

  return (
    <svg
      viewBox="0 0 720 460"
      width="100%"
      role="img"
      aria-label="Illustration preview of an isometric warehouse with shelf rows, stacked cartons, a small robot, a goal marker and a dashed route. Not a running simulation."
      style={{ display: 'block', height: 'auto' }}
    >
      <polygon
        points={toPoints(floor)}
        fill="var(--bg-panel-raised)"
        stroke="var(--border-primary)"
        strokeWidth={1}
      />
      {floorGridLines().map((line, index) => (
        <polyline
          key={`grid-${index}`}
          points={toPoints(line)}
          fill="none"
          stroke="var(--border-secondary)"
          strokeWidth={1}
        />
      ))}

      <path
        d={routePath}
        fill="none"
        stroke="var(--text-muted)"
        strokeWidth={1.5}
        strokeDasharray="5 5"
        strokeLinecap="round"
      />

      {orderedBlocks.map((block) => (
        <BlockShape key={block.id} block={block} />
      ))}

      {/* Goal marker: ring plus inner diamond. */}
      <g>
        <ellipse
          cx={goalTop.x}
          cy={goalTop.y}
          rx={18}
          ry={9}
          fill="none"
          stroke="var(--text-primary)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
        <polygon
          points={toPoints([
            { x: goalTop.x, y: goalTop.y - 8 },
            { x: goalTop.x + 8, y: goalTop.y },
            { x: goalTop.x, y: goalTop.y + 8 },
            { x: goalTop.x - 8, y: goalTop.y },
          ])}
          fill="none"
          stroke="var(--text-primary)"
          strokeWidth={1.5}
        />
      </g>

      {/* Robot: body, head, and cast shadow. */}
      <g>
        <ellipse
          cx={robotTop.x}
          cy={robotTop.y + 12}
          rx={13}
          ry={6}
          fill="var(--text-primary)"
          opacity={0.16}
        />
        <rect
          x={robotTop.x - 10}
          y={robotTop.y - 6}
          width={20}
          height={16}
          rx={3}
          fill="var(--text-primary)"
          opacity={0.85}
        />
        <rect
          x={robotTop.x - 6}
          y={robotTop.y - 13}
          width={12}
          height={7}
          rx={2}
          fill="var(--text-primary)"
          opacity={0.55}
        />
        <circle cx={robotTop.x - 3} cy={robotTop.y + 1} r={1.6} fill="var(--bg-panel)" />
        <circle cx={robotTop.x + 3} cy={robotTop.y + 1} r={1.6} fill="var(--bg-panel)" />
      </g>
    </svg>
  )
}
