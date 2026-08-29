import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { HighlightedText } from '@/components/HighlightedText'
import type { ClarificationInfo, QueryResponse } from '@/types'

export type FeedbackState = 'none' | 'sending' | 'up' | 'down'

export function AnswerCard({
  result,
  feedback,
  onConfirmSuggestion,
  onSendFeedback,
  onReset,
}: {
  result: QueryResponse
  feedback: FeedbackState
  onConfirmSuggestion: (clarification: ClarificationInfo, stationName: string) => void
  onSendFeedback: (traceId: string, thumbsUp: boolean) => void
  onReset: () => void
}) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-4 text-center">
        <p className="text-lg leading-relaxed">
          <HighlightedText text={result.text} highlights={result.highlights} />
        </p>
        {result.clarification?.suggested_station_name && (
          <Button
            onClick={() =>
              onConfirmSuggestion(
                result.clarification!,
                result.clarification!.suggested_station_name!,
              )
            }
          >
            Yes, use {result.clarification.suggested_station_name}
          </Button>
        )}
        {result.clarification?.options && (
          <div className="flex flex-col items-center gap-2">
            {result.clarification.options.map((option) => (
              <Button
                key={option}
                variant="outline"
                onClick={() => onConfirmSuggestion(result.clarification!, option)}
              >
                {option}
              </Button>
            ))}
          </div>
        )}
        {result.trace_id && (
          <div className="flex items-center justify-center gap-2 text-sm">
            {feedback === 'none' || feedback === 'sending' ? (
              <>
                <span>Was this helpful?</span>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={feedback === 'sending'}
                  onClick={() => onSendFeedback(result.trace_id!, true)}
                  aria-label="Thumbs up"
                >
                  👍
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={feedback === 'sending'}
                  onClick={() => onSendFeedback(result.trace_id!, false)}
                  aria-label="Thumbs down"
                >
                  👎
                </Button>
              </>
            ) : (
              <span>Thanks for the feedback.</span>
            )}
          </div>
        )}
        <Button variant="outline" onClick={onReset}>
          Ask another question
        </Button>
      </CardContent>
    </Card>
  )
}
