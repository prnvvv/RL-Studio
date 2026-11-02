import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RunScopeField } from './RunScopeField'

function renderField(overrides: Partial<Parameters<typeof RunScopeField>[0]> = {}) {
  const onSubmit = vi.fn()
  const result = render(<RunScopeField value="" onSubmit={onSubmit} {...overrides} />)
  return { ...result, onSubmit }
}

describe('RunScopeField', () => {
  it('associates a visible label with the identifier input', () => {
    renderField()

    const input = screen.getByLabelText('Run identifier')
    expect(input).toHaveValue('')
  })

  it('commits the trimmed identifier', () => {
    const { onSubmit } = renderField()

    fireEvent.change(screen.getByLabelText('Run identifier'), { target: { value: '  run_1 ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Use run' }))

    expect(onSubmit).toHaveBeenCalledWith('run_1')
  })

  it('rejects an empty identifier instead of silently clearing the scope', () => {
    const { onSubmit } = renderField({ value: 'run_1' })

    fireEvent.change(screen.getByLabelText('Run identifier'), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Use run' }))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a run identifier.')
    expect(screen.getByLabelText('Run identifier')).toHaveAttribute('aria-invalid', 'true')
  })

  it('adopts a scope changed outside the field', () => {
    const { rerender, onSubmit } = renderField({ value: 'run_1' })

    rerender(<RunScopeField value="run_2" onSubmit={onSubmit} />)

    expect(screen.getByLabelText('Run identifier')).toHaveValue('run_2')
  })

  it('disables the control and submit while a consequential operation is in flight', () => {
    renderField({ value: 'run_1', disabled: true })

    expect(screen.getByLabelText('Run identifier')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Use run' })).toBeDisabled()
  })
})
