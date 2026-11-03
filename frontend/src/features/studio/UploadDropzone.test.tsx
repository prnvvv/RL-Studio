import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { UploadDropzone, type UploadHooks, type UploadOutcome } from './UploadDropzone'

const file = (name: string, size = 10) => new File([new Uint8Array(size)], name)

function setup(upload: (f: File, h: UploadHooks) => Promise<UploadOutcome>, extra: Partial<Parameters<typeof UploadDropzone>[0]> = {}) {
  render(<UploadDropzone label="Drag & drop a custom model" accept={['.zip', '.pt']} hint="SB3 .zip or .pt" upload={upload} {...extra} />)
  return screen.getByTestId('upload-input') as HTMLInputElement
}

describe('UploadDropzone', () => {
  it('walks uploading → validating → ready using the real request phases', async () => {
    let finish!: (o: UploadOutcome) => void
    let hooks!: UploadHooks
    const upload = vi.fn((_f: File, h: UploadHooks) => {
      hooks = h
      return new Promise<UploadOutcome>((resolve) => {
        finish = resolve
      })
    })
    const input = setup(upload)
    fireEvent.change(input, { target: { files: [file('policy.zip')] } })

    expect(await screen.findByText(/Uploading policy\.zip/)).toBeInTheDocument()
    act(() => hooks.onProgress(0.5))
    expect(screen.getByRole('progressbar', { name: 'Upload progress' })).toHaveAttribute('aria-valuenow', '50')
    act(() => hooks.onPhase('validating'))
    expect(screen.getByText(/Validating policy\.zip/)).toBeInTheDocument()
    await act(async () => finish({ ok: true, message: 'PPO · 4 inputs → 2 actions' }))
    expect(screen.getByRole('status')).toHaveTextContent('Ready — PPO · 4 inputs → 2 actions')
  })

  it('shows the backend rejection reason as an error', async () => {
    const input = setup(async () => ({ ok: false, message: 'This model expects 8 observation values but CartPole provides 4.' }))
    fireEvent.change(input, { target: { files: [file('big.zip')] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('expects 8 observation values')
  })

  it('refuses unsupported extensions and oversize files without calling the backend', async () => {
    const upload = vi.fn()
    const input = setup(upload, { maxBytes: 100 })
    fireEvent.change(input, { target: { files: [file('model.pkl')] } })
    expect(await screen.findByRole('alert')).toHaveTextContent('Unsupported file type .pkl')
    fireEvent.change(input, { target: { files: [file('huge.zip', 1000)] } })
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('larger than'))
    expect(upload).not.toHaveBeenCalled()
  })

  it('accepts a dropped file and ignores a second drop while uploading', async () => {
    let finish!: (o: UploadOutcome) => void
    const upload = vi.fn(() => new Promise<UploadOutcome>((resolve) => (finish = resolve)))
    setup(upload)
    const zone = document.querySelector('.dropzone') as HTMLElement
    fireEvent.drop(zone, { dataTransfer: { files: [file('a.zip')] } })
    await screen.findByText(/Uploading a\.zip/)
    fireEvent.drop(zone, { dataTransfer: { files: [file('b.zip')] } })
    expect(upload).toHaveBeenCalledTimes(1)
    await act(async () => finish({ ok: true, message: 'done' }))
  })

  it('is inert while disabled', () => {
    const upload = vi.fn()
    setup(upload, { disabled: true })
    expect(screen.getByRole('button', { name: /Drag & drop a custom model/ })).toBeDisabled()
    fireEvent.drop(document.querySelector('.dropzone') as HTMLElement, { dataTransfer: { files: [file('a.zip')] } })
    expect(upload).not.toHaveBeenCalled()
  })
})
