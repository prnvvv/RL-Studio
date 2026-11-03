import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConfigPanel } from './ConfigPanel'
import { ControlToolbar } from './ControlToolbar'
import { LibraryPanel } from './LibraryPanel'
import { BipedalWalker2D } from './renderers/BipedalWalker2D'
import { LunarLander2D } from './renderers/LunarLander2D'
import { lunarEngines } from './renderers/lunarEngines'
import { MountainCar2D } from './renderers/MountainCar2D'
import type { ScenePalette } from './renderers/palette'
import { getRenderer, registeredRenderers } from './renderers/registry'
import { adaptGridObstacles, gridScene, stateNumber, statePoints } from './simulationAdapters'
import { StudioStore } from './studioStore'
import { CARTPOLE, CATALOG, PPO } from './studioFixtures'
import { emptyDraft, selectAgent, selectEnvironment } from './studioConfig'
import type { EnvironmentTemplate, FramePayload, ParamSpec } from './studioTypes'

const palette: ScenePalette = {
  background: '#000',
  floor: '#111',
  grid: '#222',
  structure: '#555',
  agent: '#fff',
  accent: '#ccc',
  good: '#0f0',
  bad: '#f00',
  text: '#aaa',
}

function frameOf(state: FramePayload['state'], extra: Partial<FramePayload> = {}): FramePayload {
  return {
    timestep: 1,
    episode: 1,
    episode_step: 1,
    action: null,
    reward: 0,
    episode_reward: 0,
    collision: false,
    disturbance: false,
    done: false,
    state,
    ...extra,
  }
}

function storeWith(frame: FramePayload): StudioStore {
  const store = new StudioStore()
  store.applyFrame(frame)
  return store
}

describe('frame state adapters', () => {
  it('reads numbers and point lists, ignoring anything of the wrong shape', () => {
    const frame = frameOf({
      x: 2.5,
      flag: true,
      terrain: [
        [0, 1],
        [2, 3],
      ],
      bad: [1, 2],
    })
    expect(stateNumber(frame, 'x')).toBe(2.5)
    expect(stateNumber(frame, 'flag', 7)).toBe(7)
    expect(stateNumber(null, 'x', 4)).toBe(4)
    expect(statePoints(frame, 'terrain')).toEqual([
      [0, 1],
      [2, 3],
    ])
    expect(statePoints(frame, 'bad')).toEqual([])
    expect(statePoints(frame, 'missing')).toEqual([])
  })

  it('draws live obstacle cells only for moving layouts, otherwise the static scene', () => {
    const base = { rows: 5, cols: 5, start: [0, 0], goal: [4, 4], obstacles: [[1, 1]] }
    const live = frameOf({ obstacles: [[2, 3]] })
    const moving = gridScene({ ...base, moving_obstacles: true })!
    const still = gridScene({ ...base, moving_obstacles: false })!
    expect(adaptGridObstacles(live, moving)).toEqual([[2, 3]])
    expect(adaptGridObstacles(live, still)).toEqual([[1, 1]])
    expect(adaptGridObstacles(null, moving)).toEqual([[1, 1]]) // before the first frame
  })
})

describe('2D renderers for the new environments', () => {
  it('registers all three without a 3D scene, so the viewport never fakes one', () => {
    for (const key of ['mountain_car', 'lunar_lander', 'bipedal_walker']) {
      expect(registeredRenderers()).toContain(key)
      expect(getRenderer(key)?.Scene3D).toBeUndefined()
      expect(getRenderer(key)?.Scene2D).toBeDefined()
    }
    expect(getRenderer('cartpole')?.Scene3D).toBeDefined()
  })

  it('maps the lander action to engines for both discrete and continuous control', () => {
    const at = (action: FramePayload['action']) => lunarEngines(frameOf({}, { action }))
    expect(at(0)).toEqual({ main: 0, side: 0 })
    expect(at(2).main).toBe(1)
    expect(at(1).side).toBe(-1)
    expect(at(3).side).toBe(1)
    expect(at([0.8, 0]).main).toBeGreaterThan(0.5)
    expect(at([-0.5, 0.9])).toEqual({ main: 0, side: 1 })
    expect(lunarEngines(frameOf({}, { action: 2, initial: true }))).toEqual({ main: 0, side: 0 })
    expect(lunarEngines(null)).toEqual({ main: 0, side: 0 })
  })

  it('draws the lander, its terrain and pad from the frame, and the main-engine flame', () => {
    const store = storeWith(
      frameOf(
        {
          x: 10,
          y: 8,
          angle: 0.1,
          left_contact: false,
          right_contact: true,
          helipad: [8, 12, 4],
          terrain: [
            [0, 3],
            [10, 4],
            [20, 3],
          ],
        },
        { action: 2 },
      ),
    )
    const { container } = render(
      <LunarLander2D scene={{ world_w: 20, world_h: 13.33 }} store={store} palette={palette} />,
    )
    expect(screen.getByRole('img', { name: 'LunarLander side view' })).toBeInTheDocument()
    expect(screen.getByTestId('engine-main')).toBeInTheDocument()
    expect(screen.queryByTestId('engine-side')).toBeNull()
    expect(container.querySelectorAll('polygon').length).toBeGreaterThanOrEqual(3)
  })

  it('draws the walker with all four legs and a finish line only when it is in view', () => {
    const legs = [
      [4.7, 4.8, 0],
      [4.6, 3.9, 0],
      [4.7, 4.8, 0.1],
      [4.6, 3.9, 0.1],
    ]
    const store = storeWith(
      frameOf({
        x: 4.6,
        y: 5.7,
        angle: 0,
        legs,
        terrain: [
          [0, 3.3],
          [10, 3.3],
        ],
      }),
    )
    render(<BipedalWalker2D scene={{ finish_x: 88.6 }} store={store} palette={palette} />)
    expect(screen.getAllByTestId('walker-leg')).toHaveLength(4)
    expect(document.querySelector('line[stroke-dasharray]')).toBeNull() // finish is 80 m away
  })

  it('draws the mountain car on the hill and flashes the push direction', () => {
    const store = storeWith(frameOf({ position: -0.5, velocity: 0.01 }, { action: 2 }))
    render(
      <MountainCar2D
        scene={{ min_position: -1.2, max_position: 0.6, goal_position: 0.5 }}
        store={store}
        palette={palette}
      />,
    )
    expect(screen.getByRole('img', { name: 'MountainCar side view' })).toBeInTheDocument()
    expect(screen.getByTestId('action-arrow')).toBeInTheDocument()
  })
})

describe('library carousels and unavailable environments', () => {
  const lander: EnvironmentTemplate = {
    ...CARTPOLE,
    key: 'lunarlander',
    name: 'LunarLander',
    renderer: 'lunar_lander',
    dimension: '2D',
    available: false,
    unavailable_reason:
      'Box2D is not installed. Install it with: pip install swig "gymnasium[box2d]"',
  }
  const lstm = { ...PPO, key: 'PPO_LSTM', name: 'PPO-LSTM', family: 'on-policy' }
  const catalog = {
    ...CATALOG,
    agents: [...CATALOG.agents, lstm],
    environments: [{ ...CARTPOLE, compatible_agents: ['PPO', 'PPO_LSTM'] }, lander],
  }
  const props = {
    catalog,
    locked: false,
    onSelectAgent: vi.fn(),
    onSelectEnvironment: vi.fn(),
    onConfigure: vi.fn(),
    uploadModel: vi.fn(),
    uploadEnvironment: vi.fn(),
    onRemove: vi.fn().mockResolvedValue(undefined),
  }

  it('shows an environment that cannot run here as disabled, with the reason, and never selects it', () => {
    render(<LibraryPanel {...props} draft={emptyDraft(catalog)} />)
    const card = screen
      .getByText('LunarLander', { selector: '.env-card__title' })
      .closest('button')!
    expect(card).toBeDisabled()
    expect(card).toHaveAttribute('title', expect.stringContaining('Box2D is not installed'))
    expect(within(card).getByText(/Unavailable: Box2D is not installed/)).toBeInTheDocument()
    fireEvent.click(card)
    expect(props.onSelectEnvironment).not.toHaveBeenCalled()
  })

  it('lays the cards out as scroll-snapping rows and names agents by their display name', () => {
    const draft = selectEnvironment(
      catalog,
      selectAgent(catalog, emptyDraft(catalog), 'PPO'),
      'cartpole',
    )
    render(<LibraryPanel {...props} draft={draft} />)
    expect(screen.getByRole('radiogroup', { name: 'Agent' })).toHaveClass('carousel__track')
    expect(screen.getByRole('radiogroup', { name: 'Environment' })).toHaveClass('carousel__track')
    const compat = screen.getByLabelText('Compatible agents')
    expect(within(compat).getByText('PPO-LSTM')).toBeInTheDocument()
    expect(within(compat).queryByText('PPO_LSTM')).toBeNull()
  })
})

describe('Environment Dynamics', () => {
  const spec = (over: Partial<ParamSpec>): ParamSpec => ({
    key: 'grid_size',
    label: 'Grid size',
    kind: 'int',
    default: 6,
    min: 5,
    max: 20,
    step: 1,
    options: [],
    help: '',
    ...over,
  })
  const dynamicEnv: EnvironmentTemplate = {
    ...CARTPOLE,
    key: 'warehouse',
    name: 'Warehouse Navigation',
    params: [
      spec({}),
      spec({ key: 'num_obstacles', label: 'Obstacles', default: 4, min: 0, max: 50 }),
      spec({
        key: 'obstacle_movement',
        label: 'Moving obstacles',
        kind: 'bool',
        default: false,
        min: null,
        max: null,
      }),
    ],
  }
  const catalog = { ...CATALOG, environments: [dynamicEnv] }
  const draft = {
    ...selectEnvironment(catalog, selectAgent(catalog, emptyDraft(catalog), 'PPO'), 'warehouse'),
  }

  it('groups the environment settings under that name, with a slider for each bounded number', () => {
    const onChange = vi.fn()
    render(
      <ConfigPanel
        catalog={catalog}
        draft={draft}
        errors={{}}
        disabled={false}
        onChange={onChange}
      />,
    )
    expect(screen.getByText('Environment Dynamics · Warehouse Navigation')).toBeInTheDocument()
    const slider = screen.getByLabelText('Grid size slider')
    expect(slider).toHaveAttribute('min', '5')
    expect(slider).toHaveAttribute('max', '20')
    fireEvent.change(slider, { target: { value: '15' } })
    expect(onChange).toHaveBeenCalledWith('env_params', 'grid_size', 15)
    expect(screen.getByLabelText('Grid size')).toHaveValue(15) // the number box follows the slider
    expect(screen.queryByLabelText('Moving obstacles slider')).toBeNull() // toggles get no slider
  })

  it('sends toggles and typed numbers too, and locks everything while a session is active', () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <ConfigPanel
        catalog={catalog}
        draft={draft}
        errors={{}}
        disabled={false}
        onChange={onChange}
      />,
    )
    fireEvent.click(screen.getByLabelText('Moving obstacles'))
    expect(onChange).toHaveBeenCalledWith('env_params', 'obstacle_movement', true)
    fireEvent.change(screen.getByLabelText('Obstacles'), { target: { value: '20' } })
    expect(onChange).toHaveBeenCalledWith('env_params', 'num_obstacles', 20)
    rerender(
      <ConfigPanel catalog={catalog} draft={draft} errors={{}} disabled onChange={onChange} />,
    )
    expect(screen.getByLabelText('Grid size slider')).toBeDisabled()
  })
})

describe('3D availability in the toolbar', () => {
  it('disables the 3D button with an explanation for environments drawn only in 2D', () => {
    const base = {
      availability: {
        initialize: true,
        train: false,
        pause: false,
        resume: false,
        stop: false,
        reset: false,
        manual: false,
      },
      status: null,
      pendingCommand: null,
      busy: null,
      speed: 4,
      initializeHint: null,
      viewMode: '2d' as const,
      webgl: true,
      onInitialize: vi.fn(),
      onCommand: vi.fn(),
      onSpeed: vi.fn(),
      onResetCamera: vi.fn(),
      onViewModeChange: vi.fn(),
      manual: { available: false, active: false, hint: null },
      onToggleManual: vi.fn(),
      compare: { active: false, available: true, onToggle: vi.fn() },
      brain: {
        active: false,
        available: false,
        onToggle: vi.fn(),
        reason: 'SAC has no inspectable action distribution',
      },
    }
    render(<ControlToolbar {...base} has3d={false} />)
    const three = screen.getByRole('button', { name: '3D' })
    expect(three).toBeDisabled()
    expect(three).toHaveAttribute('title', 'This environment is drawn in 2D only')
    expect(screen.getByRole('button', { name: 'Show heatmap' })).toHaveAttribute(
      'title',
      'SAC has no inspectable action distribution',
    )
  })
})
