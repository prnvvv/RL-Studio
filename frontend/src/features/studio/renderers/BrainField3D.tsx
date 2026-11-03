import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import type { Group, Mesh, MeshBasicMaterial } from 'three'
import { cellKey, GRID_ARROW_RADIANS, gridLookup, heatOpacity } from '../brainHelpers'
import { cellToWorld, type GridScene } from '../simulationAdapters'
import type { BrainCell } from '../studioTypes'
import type { RendererProps } from './types'

interface Props {
  grid: GridScene
  store: RendererProps['store']
  palette: RendererProps['palette']
}

/**
 * Heat tiles with a preferred-direction arrow on every free grid cell. Brighter
 * means the agent is more confident there; nothing is drawn until the backend
 * sends brain data, and tiles are driven from the render loop (no React renders).
 */
export function BrainField3D({ grid, store, palette }: Props) {
  const cells = useMemo(() => {
    const blocked = new Set(grid.obstacles.map(([r, c]) => cellKey(r, c)))
    const free: Array<[number, number]> = []
    for (let r = 0; r < grid.rows; r += 1) {
      for (let c = 0; c < grid.cols; c += 1) if (!blocked.has(cellKey(r, c))) free.push([r, c])
    }
    return free
  }, [grid])
  const planes = useRef<Array<Mesh | null>>([])
  const arrows = useRef<Array<Group | null>>([])
  const cache = useRef<{ source: BrainCell[] | undefined; map: Map<string, BrainCell> }>({
    source: undefined,
    map: new Map(),
  })

  useFrame(() => {
    const source = store.frame?.brain?.grid
    if (cache.current.source !== source) cache.current = { source, map: gridLookup(source) }
    cells.forEach(([row, col], index) => {
      const plane = planes.current[index]
      const arrow = arrows.current[index]
      if (!plane || !arrow) return
      const info = cache.current.map.get(cellKey(row, col))
      plane.visible = info !== undefined
      arrow.visible = info !== undefined
      if (!info) return
      ;(plane.material as MeshBasicMaterial).opacity = heatOpacity(info.probs)
      arrow.rotation.y = GRID_ARROW_RADIANS[info.greedy] ?? 0
    })
  })

  return (
    <group>
      {cells.map(([row, col], index) => {
        const [x, z] = cellToWorld(grid, row, col)
        return (
          <group key={cellKey(row, col)} position={[x, 0.03, z]}>
            <mesh
              ref={(mesh) => {
                planes.current[index] = mesh
              }}
              rotation={[-Math.PI / 2, 0, 0]}
              visible={false}
            >
              <planeGeometry args={[0.92, 0.92]} />
              <meshBasicMaterial color={palette.agent} transparent opacity={0} depthWrite={false} />
            </mesh>
            <group
              ref={(group) => {
                arrows.current[index] = group
              }}
              position={[0, 0.04, 0]}
              visible={false}
            >
              <mesh rotation={[Math.PI / 2, 0, 0]}>
                <coneGeometry args={[0.12, 0.34, 12]} />
                <meshBasicMaterial color={palette.accent} />
              </mesh>
            </group>
          </group>
        )
      })}
    </group>
  )
}
