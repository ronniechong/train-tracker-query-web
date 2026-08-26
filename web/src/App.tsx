import { useCallback, useRef, useState } from 'react'
import './App.css'

const MAX_RECORDING_MS = 30_000

type Stage = 'idle' | 'recording' | 'processing' | 'result' | 'error'

interface QueryResponse {
  text: string
  audio: string | null
  fallback_reason: string | null
}

function App() {
  const [stage, setStage] = useState<Stage>('idle')
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const stopTimerRef = useRef<number | null>(null)

  const submitAudio = useCallback(async (blob: Blob) => {
    setStage('processing')
    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': blob.type || 'audio/webm' },
        body: blob,
      })
      if (!response.ok) {
        const detail = await response.text()
        throw new Error(`${response.status}: ${detail}`)
      }
      const body: QueryResponse = await response.json()
      setResult(body)
      setStage('result')
      if (body.audio) {
        const audio = new Audio(`data:audio/wav;base64,${body.audio}`)
        void audio.play()
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Something went wrong.')
      setStage('error')
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

  const reset = useCallback(() => {
    setResult(null)
    setErrorMessage(null)
    setStage('idle')
  }, [])

  return (
    <main>
      <h1>Melbourne Train Times</h1>
      <p className="disclosure">
        Your voice recording is sent to Groq to transcribe your question and is
        never stored. The text of your question is kept in our logs to help
        improve answers.
      </p>

      {stage === 'idle' && (
        <button type="button" onClick={() => void startRecording()}>
          Ask a question
        </button>
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
    </main>
  )
}

export default App
