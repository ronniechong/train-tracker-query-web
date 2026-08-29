import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HighlightedText } from './HighlightedText'

describe('HighlightedText', () => {
  it('renders plain text unchanged when there are no highlights', () => {
    render(<HighlightedText text="No service today." highlights={[]} />)
    expect(screen.getByText('No service today.')).toBeInTheDocument()
  })

  it('wraps a matched highlight in its own element', () => {
    render(
      <HighlightedText
        text="Catch the 9:14am train."
        highlights={[{ text: '9:14am', kind: 'time' }]}
      />,
    )
    const highlighted = screen.getByText('9:14am')
    expect(highlighted.tagName).toBe('SPAN')
    expect(highlighted.className).toContain('font-semibold')
  })
})
