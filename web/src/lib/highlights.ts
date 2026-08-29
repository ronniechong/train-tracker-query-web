import type { Highlight, HighlightKind } from '@/types'

export interface AnswerSegment {
  text: string
  kind: HighlightKind | null
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// Highlights are exact substrings the API already knows appear verbatim in
// `text` (see service/src/pipeline/compose.py's build_highlights) -- a
// highlight that doesn't actually match (the model phrased around it) is
// simply never produced as its own segment here, never an error.
export function splitAnswerIntoSegments(text: string, highlights: Highlight[]): AnswerSegment[] {
  if (highlights.length === 0) return [{ text, kind: null }]

  const kindByText = new Map(highlights.map((h) => [h.text, h.kind]))
  const pattern = [...kindByText.keys()]
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join('|')
  const regex = new RegExp(`(${pattern})`, 'g')

  return text
    .split(regex)
    .filter((part) => part.length > 0)
    .map((part) => ({ text: part, kind: kindByText.get(part) ?? null }))
}
