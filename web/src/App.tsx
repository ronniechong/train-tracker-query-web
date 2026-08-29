import { useCallback, useRef, useState } from 'react'
import { AnswerCard, type FeedbackState } from '@/components/AnswerCard'
import { Button } from '@/components/ui/button'
import { QueryForm, type QueryTab } from '@/components/QueryForm'
import { API_BASE_URL } from '@/lib/api'
import type { ClarificationInfo, QueryResponse } from '@/types'

const MAX_RECORDING_MS = 30_000
const TRAIN_TRACKER_URL = 'https://ronniechong.com/train-tracker/'

type Stage = 'idle' | 'recording' | 'processing' | 'result' | 'error'

function playAudio(base64: string) {
  const audio = new Audio(`data:audio/wav;base64,${base64}`)
  void audio.play()
}

function App() {
  const [activeTab, setActiveTab] = useState<QueryTab>('voice')
  const [stage, setStage] = useState<Stage>('idle')
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [textInput, setTextInput] = useState('')
  const [feedback, setFeedback] = useState<FeedbackState>('none')

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const stopTimerRef = useRef<number | null>(null)

  const runQuery = useCallback(async (path: string, init: RequestInit) => {
    setStage('processing')
    try {
      const response = await fetch(path, init)
      if (!response.ok) {
        const detail = await response.text()
        throw new Error(`${response.status}: ${detail}`)
      }
      const body: QueryResponse = await response.json()
      setResult(body)
      setFeedback('none')
      setStage('result')
      if (body.audio) playAudio(body.audio)
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Something went wrong.')
      setStage('error')
    }
  }, [])

  const submitAudio = useCallback(
    (blob: Blob) =>
      runQuery(`${API_BASE_URL}/api/query`, {
        method: 'POST',
        headers: { 'Content-Type': blob.type || 'audio/webm' },
        body: blob,
      }),
    [runQuery],
  )

  const submitText = useCallback(
    (text: string) =>
      runQuery(`${API_BASE_URL}/api/query/text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }),
    [runQuery],
  )

  const confirmSuggestion = useCallback(
    (clarification: ClarificationInfo, stationName: string) => {
      const field = `${clarification.field}_station`
      const body = { ...clarification.extracted, [field]: stationName }
      return runQuery(`${API_BASE_URL}/api/query/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    },
    [runQuery],
  )

  const sendFeedback = useCallback(async (traceId: string, thumbsUp: boolean) => {
    setFeedback('sending')
    try {
      await fetch(`${API_BASE_URL}/api/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trace_id: traceId, thumbs_up: thumbsUp }),
      })
      setFeedback(thumbsUp ? 'up' : 'down')
    } catch {
      setFeedback('none')
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (stopTimerRef.current !== null) {
      window.clearTimeout(stopTimerRef.current)
      stopTimerRef.current = null
    }
    mediaRecorderRef.current?.stop()
  }, [])

  const startRecording = useCallback(async () => {
    setResult(null)
    setErrorMessage(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop())
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType })
        void submitAudio(blob)
      }

      mediaRecorderRef.current = recorder
      recorder.start()
      setStage('recording')
      stopTimerRef.current = window.setTimeout(stopRecording, MAX_RECORDING_MS)
    } catch {
      setErrorMessage('Microphone access is needed to ask a question by voice.')
      setStage('error')
    }
  }, [stopRecording, submitAudio])

  const handleTextSubmit = useCallback(
    (event: React.FormEvent) => {
      event.preventDefault()
      const text = textInput.trim()
      if (!text) return
      setResult(null)
      setErrorMessage(null)
      void submitText(text)
    },
    [textInput, submitText],
  )

  const reset = useCallback(() => {
    setResult(null)
    setErrorMessage(null)
    setTextInput('')
    setStage('idle')
  }, [])

  return (
    <div className="flex min-h-screen flex-col items-center bg-background px-6 py-10 text-foreground">
      <div className="flex w-full max-w-lg flex-1 flex-col items-center">
        <header className="mb-8 flex flex-col items-center gap-2">
          <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" className="h-10 w-10" />
          <h1 className="text-center text-2xl font-semibold tracking-tight">
            Ask Melbourne Train Tracker
          </h1>
        </header>

        <main className="w-full">
          {stage === 'idle' && (
            <QueryForm
              activeTab={activeTab}
              onTabChange={setActiveTab}
              onStartRecording={() => void startRecording()}
              textInput={textInput}
              onTextInputChange={setTextInput}
              onTextSubmit={handleTextSubmit}
            />
          )}

          {stage === 'recording' && (
            <div className="flex flex-col items-center gap-4">
              <p className="text-destructive">Listening… (stops automatically after 30 seconds)</p>
              <Button variant="outline" onClick={stopRecording}>
                Stop
              </Button>
            </div>
          )}

          {stage === 'processing' && (
            <div className="flex flex-col items-center gap-4">
              <p className="text-muted-foreground">Working on your answer…</p>
            </div>
          )}

          {stage === 'result' && result && (
            <AnswerCard
              result={result}
              feedback={feedback}
              onConfirmSuggestion={(clarification, station) =>
                void confirmSuggestion(clarification, station)
              }
              onSendFeedback={(traceId, thumbsUp) => void sendFeedback(traceId, thumbsUp)}
              onReset={reset}
            />
          )}

          {stage === 'error' && (
            <div className="flex flex-col items-center gap-4">
              <p className="text-muted-foreground">{errorMessage}</p>
              <Button variant="outline" onClick={reset}>
                Try again
              </Button>
            </div>
          )}
        </main>
      </div>

      <footer className="mt-10 max-w-lg text-center text-xs text-muted-foreground">
        <p>We do not store your voice recording.</p>
        <p className="mt-1">
          This is an experimental project and should not be relied on for real train times. For trip
          planning, use the{' '}
          <a href={TRAIN_TRACKER_URL} className="underline underline-offset-2">
            Train Tracker
          </a>{' '}
          website.
        </p>
      </footer>
    </div>
  )
}

export default App
