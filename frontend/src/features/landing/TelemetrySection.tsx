import { useReveal } from './useReveal'

/**
 * A static bar sketch of a training signal. It is decorative: it does not plot data and is
 * hidden from assistive technology.
 */
const BARS = Array.from({ length: 30 }, (_, i) => {
  const wave = Math.sin(i * 0.55) * 0.22 + Math.sin(i * 1.35 + 1) * 0.12
  const trend = 0.3 + (i / 29) * 0.38
  return Math.round(Math.min(1, Math.max(0.12, trend + wave)) * 100)
})

/** Illustrative sample lines. They are written out here on purpose and are labelled as a sample. */
const LINES: Array<{ parts: Array<{ text: string; strong?: boolean }> }> = [
  {
    parts: [
      { text: 'Initializing environment: ' },
      { text: 'WarehouseNavigation-v0', strong: true },
    ],
  },
  {
    parts: [
      { text: 'Agent: ' },
      { text: 'PPO', strong: true },
      { text: ' | Policy: ' },
      { text: 'MlpPolicy', strong: true },
    ],
  },
  { parts: [{ text: 'Training...' }] },
  ...[
    ['10000', '8.72', '0.034'],
    ['20000', '9.31', '0.028'],
    ['30000', '9.85', '0.021'],
  ].map(([step, reward, loss]) => ({
    parts: [
      { text: 'Step ' },
      { text: step, strong: true },
      { text: ' | Reward: ' },
      { text: reward, strong: true },
      { text: ' | Loss: ' },
      { text: loss, strong: true },
      { text: ' | Status: ' },
      { text: 'Healthy', strong: true },
    ],
  })),
]

export function TelemetrySection() {
  const { ref, visible } = useReveal<HTMLDivElement>()
  return (
    <section id="telemetry" className="ls-telemetry" aria-labelledby="ls-telemetry-title">
      <div ref={ref} className="ls-terminal" data-reveal="" data-in={visible ? '' : undefined}>
        <div className="ls-terminal__bar">
          <span className="ls-terminal__dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span className="ls-terminal__label">Live telemetry</span>
          <span className="ls-terminal__label ls-terminal__label--right">
            Training stream · illustrative sample
          </span>
        </div>

        <div className="ls-terminal__body">
          <div className="ls-terminal__intro">
            <h2 id="ls-telemetry-title" className="ls-terminal__title">
              Live telemetry
            </h2>
            <p>Real-time training and recovery signals from your agents.</p>
            <div className="ls-wave" aria-hidden="true">
              {BARS.map((height, index) => (
                <span key={index} style={{ ['--h' as string]: `${height}%` }} />
              ))}
            </div>
            <p className="ls-terminal__note">Sample output for illustration, not a live feed.</p>
          </div>

          <figure className="ls-terminal__log" aria-label="Illustrative training log">
            <div className="ls-terminal__lines">
              {LINES.map((line, index) => (
                <p key={index} className="ls-term__line">
                  <span className="ls-term__prompt" aria-hidden="true">
                    &gt;
                  </span>
                  {line.parts.map((part, partIndex) =>
                    part.strong ? (
                      <b key={partIndex}>{part.text}</b>
                    ) : (
                      <span key={partIndex}>{part.text}</span>
                    ),
                  )}
                </p>
              ))}
              <p className="ls-term__line ls-term__line--cursor" aria-hidden="true">
                <span className="ls-term__prompt">&gt;</span>
                <span className="ls-term__cursor" />
              </p>
            </div>
          </figure>
        </div>
      </div>
    </section>
  )
}
