import { useCallback, useRef } from 'react'

export function useAudioRecorder(onStopRecording) {
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }, [])

  const startRecording = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    streamRef.current = stream
    const recorder = new MediaRecorder(stream)
    mediaRecorderRef.current = recorder
    chunksRef.current = []
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }
    recorder.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: 'audio/wav' })
      chunksRef.current = []
      onStopRecording(blob)
    }
    recorder.start(200)
  }, [onStopRecording])

  return { startRecording, stopRecording }
}
