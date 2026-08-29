export interface ExtractedQueryFields {
  from_station: string | null
  to_station: string | null
  route_hint: string | null
  time: string | null
}

export interface ClarificationInfo {
  field: string
  suggested_station_name: string | null
  options: string[] | null
  extracted: ExtractedQueryFields
}

export type HighlightKind = 'station' | 'platform' | 'time'

export interface Highlight {
  text: string
  kind: HighlightKind
}

export interface QueryResponse {
  text: string
  audio: string | null
  fallback_reason: string | null
  clarification: ClarificationInfo | null
  trace_id: string | null
  highlights: Highlight[]
}
