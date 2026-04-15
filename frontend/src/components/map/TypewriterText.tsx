/* WorldSeed — TypewriterText: layout-stable typewriter reveal.
 *
 * Invisible full text holds layout; visible typewriter overlays on top.
 * Prevents container size changes during character-by-character reveal.
 * Used by OverlayBubble (speech/description) and NarrativeBar.
 */

interface Props {
  /** Full text (what the container should be sized for) */
  fullText: string
  /** Currently displayed text (partial during typewriter, full when done) */
  displayedText: string
  /** Whether typewriter is complete */
  isDone: boolean
  /** Additional className for the text container */
  className?: string
  /** Inline style for the text container */
  style?: React.CSSProperties
}

export default function TypewriterText({ fullText, displayedText, isDone, className, style }: Props) {
  return (
    <div className={`relative ${className || ''}`} style={style}>
      <span style={{ visibility: 'hidden' }}>{fullText}</span>
      <span className={`absolute inset-0 ${isDone ? '' : 'tw-text'}`}>{displayedText}</span>
    </div>
  )
}
