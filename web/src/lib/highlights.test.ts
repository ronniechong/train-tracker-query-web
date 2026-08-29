import { describe, expect, it } from 'vitest'
import { splitAnswerIntoSegments } from './highlights'

describe('splitAnswerIntoSegments', () => {
  it('returns the whole text as one unkindled segment when there are no highlights', () => {
    expect(splitAnswerIntoSegments('Catch the 9:14am train.', [])).toEqual([
      { text: 'Catch the 9:14am train.', kind: null },
    ])
  })

  it('splits out a single matching highlight', () => {
    const segments = splitAnswerIntoSegments('Catch the 9:14am from Richmond Station.', [
      { text: 'Richmond Station', kind: 'station' },
    ])
    expect(segments).toEqual([
      { text: 'Catch the 9:14am from ', kind: null },
      { text: 'Richmond Station', kind: 'station' },
      { text: '.', kind: null },
    ])
  })

  it('splits out multiple highlights of different kinds', () => {
    const segments = splitAnswerIntoSegments(
      'Catch the 9:14am from Richmond Station on Platform 3 to Flinders Street Station, arriving 9:28am.',
      [
        { text: 'Richmond Station', kind: 'station' },
        { text: 'Flinders Street Station', kind: 'station' },
        { text: 'Platform 3', kind: 'platform' },
        { text: '9:14am', kind: 'time' },
        { text: '9:28am', kind: 'time' },
      ],
    )
    const kinds = segments.filter((s) => s.kind).map((s) => `${s.kind}:${s.text}`)
    expect(kinds).toEqual([
      'time:9:14am',
      'station:Richmond Station',
      'platform:Platform 3',
      'station:Flinders Street Station',
      'time:9:28am',
    ])
  })

  it('prefers the longer overlapping match (station name is not cut short by a shorter substring)', () => {
    const segments = splitAnswerIntoSegments('Arriving at Flinders Street Station now.', [
      { text: 'Flinders Street Station', kind: 'station' },
      { text: 'Street Station', kind: 'station' },
    ])
    expect(segments.filter((s) => s.kind)).toEqual([
      { text: 'Flinders Street Station', kind: 'station' },
    ])
  })

  it('silently produces no highlighted segment for a highlight that never appears verbatim', () => {
    const segments = splitAnswerIntoSegments('Sorry, no service found today.', [
      { text: 'Richmond Station', kind: 'station' },
    ])
    expect(segments.every((s) => s.kind === null)).toBe(true)
    expect(segments.map((s) => s.text).join('')).toBe('Sorry, no service found today.')
  })

  it('escapes regex special characters in highlight text', () => {
    const segments = splitAnswerIntoSegments('Cost: $5.00 (approx).', [
      { text: '$5.00', kind: 'time' },
    ])
    expect(segments.filter((s) => s.kind)).toEqual([{ text: '$5.00', kind: 'time' }])
  })
})
