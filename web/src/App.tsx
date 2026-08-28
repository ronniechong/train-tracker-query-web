import { useCallback, useRef, useState } from 'react'
import './App.css'
import { API_BASE_URL } from './config'

const MAX_RECORDING_MS = 30_000

type Stage = 'idle' | 'recording' | 'processing' | 'result' | 'error'

interface ExtractedQueryFields {
  from_station: string | null
  to_station: string | null
  route_hint: string | null
  time: string | null
}

interface ClarificationInfo {
  field: string
  suggested_station_name: string | null
  options: string[] | null
  extracted: ExtractedQueryFields
}

interface QueryResponse {
  text: string
  audio: string | null
  fallback_reason: string | null
  clarification: ClarificationInfo | null
  trace_id: string | null
}

type FeedbackState = 'none' | 'sending' | 'up' | 'down'

function playAudio(base64: string) {
  const audio = new Audio(`data:audio/wav;base64,${base64}`)
  void audio.play()
}

function App() {
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
    <main>
      <h1>Melbourne Train Times</h1>

      {stage === 'idle' && (
        <div className="idle-controls">
          <button type="button" onClick={() => void startRecording()}>
            Ask a question
          </button>
          <form className="text-form" onSubmit={handleTextSubmit}>
            <input
              type="text"
              placeholder="Or type your question…"
              value={textInput}
              onChange={(event) => setTextInput(event.target.value)}
            />
            <button type="submit" disabled={!textInput.trim()}>
              Ask
            </button>
          </form>
        </div>
      )}

      {stage === 'recording' && (
        <div className="status status-recording">
          <p>Listening… (stops automatically after 30 seconds)</p>
          <button type="button" onClick={stopRecording}>
            Stop
          </button>
        </div>
      )}

      {stage === 'processing' && (
        <div className="status status-processing">
          <p>Working on your answer…</p>
        </div>
      )}

      {stage === 'result' && result && (
        <div className={`status ${result.fallback_reason ? 'status-fallback' : 'status-answer'}`}>
          <p>{result.text}</p>
          {result.clarification?.suggested_station_name && (
            <button
              type="button"
              onClick={() =>
                void confirmSuggestion(result.clarification!, result.clarification!.suggested_station_name!)
              }
            >
              Yes, use {result.clarification.suggested_station_name}
            </button>
          )}
          {result.clarification?.options && (
            <div className="clarification-options">
              {result.clarification.options.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => void confirmSuggestion(result.clarification!, option)}
                >
                  {option}
                </button>
              ))}
            </div>
          )}
          {result.trace_id && (
            <div className="feedback">
              {feedback === 'none' || feedback === 'sending' ? (
                <>
                  <span>Was this helpful?</span>
                  <button
                    type="button"
                    disabled={feedback === 'sending'}
                    onClick={() => void sendFeedback(result.trace_id!, true)}
                    aria-label="Thumbs up"
                  >
                    👍
                  </button>
                  <button
                    type="button"
                    disabled={feedback === 'sending'}
                    onClick={() => void sendFeedback(result.trace_id!, false)}
                    aria-label="Thumbs down"
                  >
                    👎
                  </button>
                </>
              ) : (
                <span>Thanks for the feedback.</span>
              )}
            </div>
          )}
          <button type="button" onClick={reset}>
            Ask another question
          </button>
        </div>
      )}

      {stage === 'error' && (
        <div className="status status-fallback">
          <p>{errorMessage}</p>
          <button type="button" onClick={reset}>
            Try again
          </button>
        </div>
      )}

      <p className="fine-print">We do not store your voice recording.</p>
    </main>
  )
}

export default App
