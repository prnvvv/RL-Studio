import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import {
  BufferGeometry,
  Line as ThreeLine,
  LineBasicMaterial,
  MathUtils,
  Vector3,
  type Group,
  type Mesh,
  type MeshStandardMaterial,
} from 'three'
import { adaptGridAgent, cellToWorld, gridScene } from '../simulationAdapters'
import { BrainField3D } from './BrainField3D'
import type { RendererProps } from './types'

const WALL_HEIGHT = 0.8
const AGENT_RADIUS = 0.28
const TRAIL_LENGTH = 40
const DAMPING = 18

/** 3D warehouse maze: extruded obstacles, goal marker, animated agent and trail. */
export function GridMaze3D({ scene, store, palette }: RendererProps) {
  const grid = gridScene(scene)
  const agent = useRef<Group>(null)
  const agentMaterial = useRef<MeshStandardMaterial>(null)
  const goalMarker = useRef<Mesh>(null)
  const trailPoints = useRef<Array<[number, number, number]>>([])
  const lastCell = useRef<string>('')
  const lastEpisode = useRef(-1)
  const trail = useMemo(
    () =>
      new ThreeLine(
        new BufferGeometry(),
        new LineBasicMaterial({ transparent: true, opacity: 0.7 }),
      ),
    [],
  )

  const world = useMemo(
    () => (grid ? { goal: cellToWorld(grid, grid.goal[0], grid.goal[1]) } : null),
    [grid],
  )

  useFrame((state, delta) => {
    if (!grid) return
    const frame = store.frame
    const [row, col] = adaptGridAgent(frame, grid)
    const [x, z] = cellToWorld(grid, row, col)
    if (agent.current) {
      agent.current.position.x = MathUtils.damp(agent.current.position.x, x, DAMPING, delta)
      agent.current.position.z = MathUtils.damp(agent.current.position.z, z, DAMPING, delta)
    }
    if (agentMaterial.current) {
      agentMaterial.current.color.set(frame?.collision ? palette.bad : palette.agent)
    }
    if (goalMarker.current) {
      goalMarker.current.rotation.y = state.clock.elapsedTime
      goalMarker.current.position.y = 0.45 + Math.sin(state.clock.elapsedTime * 2) * 0.05
    }
    // Trail: restart each episode, append when the agent changes cell.
    const episode = frame?.episode ?? 0
    const here: [number, number, number] = [x, 0.05, z]
    if (episode !== lastEpisode.current) {
      lastEpisode.current = episode
      trailPoints.current = [here, here]
      lastCell.current = `${row},${col}`
    } else if (`${row},${col}` !== lastCell.current) {
      lastCell.current = `${row},${col}`
      trailPoints.current = [...trailPoints.current, here].slice(-TRAIL_LENGTH)
    }
    ;(trail.material as LineBasicMaterial).color.set(palette.accent)
    trail.geometry.setFromPoints(trailPoints.current.map(([px, py, pz]) => new Vector3(px, py, pz)))
  })

  if (!grid || !world) return null
  const [gx, gz] = world.goal
  const [startX, startZ] = cellToWorld(grid, grid.start[0], grid.start[1])

  return (
    <group>
      <ambientLight intensity={0.7} />
      <directionalLight position={[grid.cols, 10, grid.rows]} intensity={1.5} />
      <mesh position={[0, -0.05, 0]}>
        <boxGeometry args={[grid.cols, 0.1, grid.rows]} />
        <meshStandardMaterial color={palette.floor} />
      </mesh>
      <gridHelper
        args={[
          Math.max(grid.rows, grid.cols),
          Math.max(grid.rows, grid.cols),
          palette.grid,
          palette.grid,
        ]}
        position={[0, 0.001, 0]}
        scale={[
          grid.cols / Math.max(grid.rows, grid.cols),
          1,
          grid.rows / Math.max(grid.rows, grid.cols),
        ]}
      />
      {grid.obstacles.map(([r, c]) => {
        const [ox, oz] = cellToWorld(grid, r, c)
        return (
          <mesh key={`${r}-${c}`} position={[ox, WALL_HEIGHT / 2, oz]}>
            <boxGeometry args={[0.9, WALL_HEIGHT, 0.9]} />
            <meshStandardMaterial color={palette.structure} />
          </mesh>
        )
      })}
      <mesh position={[gx, 0.02, gz]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.3, 0.42, 32]} />
        <meshStandardMaterial color={palette.good} />
      </mesh>
      <mesh ref={goalMarker} position={[gx, 0.45, gz]}>
        <octahedronGeometry args={[0.18]} />
        <meshStandardMaterial
          color={palette.good}
          emissive={palette.good}
          emissiveIntensity={0.5}
        />
      </mesh>
      <BrainField3D grid={grid} store={store} palette={palette} />
      <primitive object={trail} />
      <group ref={agent} position={[startX, AGENT_RADIUS, startZ]}>
        <mesh>
          <sphereGeometry args={[AGENT_RADIUS, 24, 24]} />
          <meshStandardMaterial ref={agentMaterial} color={palette.agent} />
        </mesh>
      </group>
    </group>
  )
}
