import { splitAnswerIntoSegments } from '@/lib/highlights'
import type { Highlight, HighlightKind } from '@/types'

const HIGHLIGHT_CLASSES: Record<HighlightKind, string> = {
  station: 'text-blue-600 dark:text-blue-400 font-semibold',
  platform: 'text-violet-600 dark:text-violet-400 font-semibold',
  time: 'text-emerald-600 dark:text-emerald-400 font-semibold',
}

export function HighlightedText({ text, highlights }: { text: string; highlights: Highlight[] }) {
  return (
    <>
      {splitAnswerIntoSegments(text, highlights).map((segment, i) =>
        segment.kind ? (
          <span key={i} className={HIGHLIGHT_CLASSES[segment.kind]}>
            {segment.text}
          </span>
        ) : (
          <span key={i}>{segment.text}</span>
        ),
      )}
    </>
  )
}
