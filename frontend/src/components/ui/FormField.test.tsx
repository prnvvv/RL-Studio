import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { FormField } from './FormField'
import { TextArea } from './TextArea'

describe('TextArea', () => {
  it('stays controlled and reports changes', () => {
    function Harness() {
      const [value, setValue] = useState('')
      return (
        <TextArea
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-label="Intent"
        />
      )
    }
    render(<Harness />)
    const area = screen.getByRole('textbox', { name: 'Intent' }) as HTMLTextAreaElement
    fireEvent.change(area, { target: { value: 'Goal reward must equal 100.' } })
    expect(area.value).toBe('Goal reward must equal 100.')
  })

  it('marks invalid controls for assistive tech without colour-only signal', () => {
    render(<TextArea value="" onChange={() => undefined} invalid aria-label="Intent" />)
    expect(screen.getByRole('textbox', { name: 'Intent' })).toHaveAttribute('aria-invalid', 'true')
  })
})

describe('FormField', () => {
  it('associates the visible label, hint, and error with the control', () => {
    render(
      <FormField label="Intent" hint="Describe expected behaviour." error="Intent cannot be empty.">
        {(props) => <TextArea value="" onChange={() => undefined} {...props} />}
      </FormField>,
    )

    const area = screen.getByLabelText('Intent') as HTMLTextAreaElement
    expect(area).toHaveAttribute('aria-invalid', 'true')

    const describedBy = area.getAttribute('aria-describedby') ?? ''
    // The hint text also lives inside the described-by region.
    for (const text of ['Describe expected behaviour.', 'Intent cannot be empty.']) {
      const messageId = text.includes('cannot') ? screen.getByRole('alert') : screen.getByText(text)
      expect(describedBy).toContain(messageId.id)
    }
  })

  it('links label clicks to the control and omits invalid marker without error', () => {
    render(
      <FormField label="Seed" hint="Reproducibility seed.">
        {(props) => <input type="text" {...props} />}
      </FormField>,
    )

    const input = screen.getByLabelText('Seed')
    expect(input).not.toHaveAttribute('aria-invalid')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
