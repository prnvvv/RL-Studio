import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { EnvironmentPreview, AgentGraph } from './libraryVisuals'
import { LibraryPanel } from './LibraryPanel'
import { CATALOG } from './studioFixtures'
import { emptyDraft, selectAgent, selectEnvironment } from './studioConfig'

const props = {
  catalog: CATALOG,
  locked: false,
  onSelectAgent: vi.fn(),
  onSelectEnvironment: vi.fn(),
  onConfigure: vi.fn(),
  uploadModel: vi.fn(),
  uploadEnvironment: vi.fn(),
  onRemove: vi.fn().mockResolvedValue(undefined),
}

describe('LibraryPanel card redesign', () => {
  it('shows real counts, the policy family badge and the action spaces', () => {
    render(<LibraryPanel {...props} draft={emptyDraft(CATALOG)} />)
    expect(screen.getByLabelText(`${CATALOG.agents.length} agents`)).toBeInTheDocument()
    expect(screen.getByLabelText(`${CATALOG.environments.length} environments`)).toBeInTheDocument()
    const ppo = screen.getByText('PPO', { selector: '.agent-card__abbr' }).closest('button')!
    expect(within(ppo).getByText('on-policy')).toBeInTheDocument()
    expect(within(ppo).getByText('Discrete')).toBeInTheDocument()
    expect(within(ppo).getByText('Box')).toBeInTheDocument()
  })

  it('derives the full algorithm name from the backend description', () => {
    render(<LibraryPanel {...props} draft={emptyDraft(CATALOG)} />)
    expect(screen.getByText('Proximal Policy Optimization')).toBeInTheDocument()
  })

  it('marks exactly the selected agent and environment, and reports them to the parent', () => {
    const draft = selectEnvironment(
      CATALOG,
      selectAgent(CATALOG, emptyDraft(CATALOG), 'PPO'),
      'cartpole',
    )
    const { container } = render(<LibraryPanel {...props} draft={draft} />)
    const checked = screen
      .getAllByRole('radio')
      .filter((r) => r.getAttribute('aria-checked') === 'true')
    expect(checked).toHaveLength(2)
    expect(container.querySelectorAll('.check-badge')).toHaveLength(2)
    fireEvent.click(screen.getByRole('radio', { name: /My policy/ }))
    expect(props.onSelectAgent).toHaveBeenCalledWith('custom:mdl_abcdef123456')
  })

  it('lists only real compatibility metadata for the selected environment', () => {
    const draft = selectEnvironment(CATALOG, emptyDraft(CATALOG), 'cartpole')
    render(<LibraryPanel {...props} draft={draft} />)
    const compat = screen.getByLabelText('Compatible agents')
    const cartpole = CATALOG.environments.find((env) => env.key === 'cartpole')!
    const expected = cartpole.compatible_agents.filter((key) => !key.startsWith('custom:'))
    expect(
      within(compat)
        .getAllByText(/^[A-Z0-9]+$/)
        .map((n) => n.textContent),
    ).toEqual(expected)
  })

  it('freezes selection while a session is active', () => {
    render(<LibraryPanel {...props} locked draft={emptyDraft(CATALOG)} />)
    for (const radio of screen.getAllByRole('radio')) expect(radio).toBeDisabled()
  })
})

describe('library illustrations', () => {
  it('draws an uploaded grid exactly as declared', () => {
    const layout = {
      rows: 4,
      cols: 5,
      start: [0, 0],
      goal: [3, 4],
      obstacles: [
        [1, 1],
        [2, 3],
        [0, 2],
      ],
    }
    const { container } = render(
      <EnvironmentPreview envKey="custom:env_1" renderer="warehouse" layout={layout} />,
    )
    // One filled square per obstacle, plus the board outline.
    expect(container.querySelectorAll('rect[fill-opacity="0.45"]')).toHaveLength(3)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })

  it('has distinct illustrations for the built-in environments and a neutral fallback', () => {
    const markup = (key: string) =>
      render(<EnvironmentPreview envKey={key} renderer={key} />).container.innerHTML
    const cartpole = markup('cartpole')
    const warehouse = markup('warehouse')
    expect(cartpole).not.toBe(warehouse)
    expect(markup('something-new')).not.toBe(cartpole)
  })

  it('draws a different decorative curve per algorithm, and none for unknown ones', () => {
    const path = (key: string) =>
      render(<AgentGraph agentKey={key} />)
        .container.querySelector('path[stroke-width="1.6"]')
        ?.getAttribute('d')
    expect(new Set([path('PPO'), path('A2C'), path('DQN')]).size).toBe(3)
    expect(render(<AgentGraph agentKey="custom" />).container.querySelector('svg')).toBeNull()
  })
})
