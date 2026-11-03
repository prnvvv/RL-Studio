import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { MathUtils, type Group, type MeshBasicMaterial, type MeshStandardMaterial } from 'three'
import { adaptCartPole, cartPoleActionDirection, cartPoleScene } from '../simulationAdapters'
import { makeFadedGridTexture } from './groundGrid'
import type { RendererProps } from './types'

const DAMPING = 28
/** Seconds the action arrow takes to fade after the agent pushes. */
const FLASH_SECONDS = 0.4
const ARROW_OFFSET = 0.55

/**
 * 3D CartPole. Poses are read from `store.frame` inside the render loop, so
 * the 30 Hz backend stream never triggers a React render.
 */
export function CartPole3D({ scene, store, palette }: RendererProps) {
  const dims = cartPoleScene(scene)
  const cart = useRef<Group>(null)
  const pole = useRef<Group>(null)
  const poleMaterial = useRef<MeshStandardMaterial>(null)
  const arrow = useRef<Group>(null)
  const arrowMaterial = useRef<MeshBasicMaterial>(null)
  const brainArrows = useRef<Array<Group | null>>([null, null])
  const brainMaterials = useRef<Array<MeshBasicMaterial | null>>([null, null])
  const flash = useRef(0)
  const direction = useRef<1 | -1>(1)
  const seenFrame = useRef(-1)

  const gridTexture = useMemo(() => makeFadedGridTexture(palette.grid), [palette.grid])
  useEffect(() => () => gridTexture?.dispose(), [gridTexture])

  useFrame((_, delta) => {
    const frame = store.frame
    const pose = adaptCartPole(frame, dims)
    if (cart.current)
      cart.current.position.x = MathUtils.damp(cart.current.position.x, pose.cartX, DAMPING, delta)
    if (pole.current)
      pole.current.rotation.z = MathUtils.damp(
        pole.current.rotation.z,
        -pose.poleAngle,
        DAMPING,
        delta,
      )
    if (poleMaterial.current) {
      const failed = frame?.done === true && frame.outcome?.success === false
      poleMaterial.current.color.set(failed ? palette.bad : palette.agent)
    }

    // Flash a directional arrow whenever a new frame carries a push action.
    if (store.frameVersion !== seenFrame.current) {
      seenFrame.current = store.frameVersion
      const push = cartPoleActionDirection(frame)
      if (push !== 0) {
        flash.current = 1
        direction.current = push
      }
    }
    flash.current = Math.max(0, flash.current - delta / FLASH_SECONDS)
    if (arrow.current && cart.current) {
      arrow.current.position.x = cart.current.position.x + direction.current * ARROW_OFFSET
      arrow.current.rotation.z = direction.current === 1 ? -Math.PI / 2 : Math.PI / 2
    }
    if (arrowMaterial.current) arrowMaterial.current.opacity = flash.current

    // Brain view: arrow length and opacity follow the probability of pushing each way.
    const probs = frame?.brain?.probs
    brainArrows.current.forEach((group, side) => {
      const material = brainMaterials.current[side]
      if (!group || !material) return
      const p = probs?.[side]
      group.visible = p !== undefined && cart.current !== null
      if (p === undefined || !cart.current) return
      const dir = side === 0 ? -1 : 1
      group.position.x = cart.current.position.x + dir * (0.75 + 0.4 * p)
      group.scale.set(1, 0.4 + 2.4 * p, 1)
      material.opacity = 0.25 + 0.7 * p
    })
  })

  const trackLength = dims.x_limit * 2 + 0.8

  return (
    <group>
      <ambientLight intensity={0.8} />
      <directionalLight position={[3, 5, 4]} intensity={1.4} />
      <mesh position={[0, -0.06, 0]}>
        <boxGeometry args={[trackLength, 0.04, 0.4]} />
        <meshStandardMaterial color={palette.floor} />
      </mesh>
      {[-dims.x_limit, dims.x_limit].map((x) => (
        <mesh key={x} position={[x, 0.2, 0]}>
          <boxGeometry args={[0.05, 0.5, 0.4]} />
          <meshStandardMaterial color={palette.structure} />
        </mesh>
      ))}
      {gridTexture && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.085, 0]}>
          <planeGeometry args={[18, 18]} />
          <meshBasicMaterial map={gridTexture} transparent depthWrite={false} />
        </mesh>
      )}
      <group ref={cart} position={[0, 0.1, 0]}>
        <mesh>
          <boxGeometry args={[0.5, 0.2, 0.3]} />
          <meshStandardMaterial color={palette.accent} />
        </mesh>
        <group ref={pole} position={[0, 0.1, 0]}>
          <mesh position={[0, dims.pole_length / 2, 0]}>
            <cylinderGeometry args={[0.035, 0.035, dims.pole_length, 20]} />
            <meshStandardMaterial ref={poleMaterial} color={palette.agent} />
          </mesh>
          <mesh position={[0, dims.pole_length, 0]}>
            <sphereGeometry args={[0.08, 20, 20]} />
            <meshStandardMaterial color={palette.agent} />
          </mesh>
        </group>
      </group>
      {[0, 1].map((side) => (
        <group
          key={`brain-${side}`}
          ref={(group) => {
            brainArrows.current[side] = group
          }}
          position={[0, 0.5, 0]}
          rotation={[0, 0, side === 0 ? Math.PI / 2 : -Math.PI / 2]}
          visible={false}
        >
          <mesh>
            <coneGeometry args={[0.07, 0.3, 14]} />
            <meshBasicMaterial
              ref={(material) => {
                brainMaterials.current[side] = material
              }}
              color={palette.accent}
              transparent
              opacity={0}
            />
          </mesh>
        </group>
      ))}
      <group ref={arrow} position={[ARROW_OFFSET, 0.1, 0]}>
        <mesh>
          <coneGeometry args={[0.1, 0.24, 20]} />
          <meshBasicMaterial ref={arrowMaterial} color={palette.agent} transparent opacity={0} />
        </mesh>
      </group>
    </group>
  )
}
