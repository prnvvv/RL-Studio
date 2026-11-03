import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { MathUtils, type Group, type MeshStandardMaterial } from 'three'
import { adaptCartPole, cartPoleScene } from '../simulationAdapters'
import type { RendererProps } from './types'

const DAMPING = 28

/**
 * 3D CartPole. Poses are read from `store.frame` inside the render loop, so
 * the 30 Hz backend stream never triggers a React render.
 */
export function CartPole3D({ scene, store, palette }: RendererProps) {
  const dims = cartPoleScene(scene)
  const cart = useRef<Group>(null)
  const pole = useRef<Group>(null)
  const poleMaterial = useRef<MeshStandardMaterial>(null)

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
      <gridHelper args={[12, 24, palette.grid, palette.grid]} position={[0, -0.09, 0]} />
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
    </group>
  )
}
