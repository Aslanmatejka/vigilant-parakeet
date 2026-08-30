import { pickMediaRecorderMimeType, createMediaRecorder } from '../utils/mediaRecorder'

describe('mediaRecorder helpers', () => {
  const originalMediaRecorder = global.MediaRecorder

  afterEach(() => {
    global.MediaRecorder = originalMediaRecorder
  })

  it('pickMediaRecorderMimeType prefers webm opus when supported', () => {
    global.MediaRecorder = class {
      static isTypeSupported(type) {
        return type === 'audio/webm;codecs=opus' || type === 'audio/mp4'
      }
    }
    expect(pickMediaRecorderMimeType()).toBe('audio/webm;codecs=opus')
  })

  it('pickMediaRecorderMimeType falls back to mp4 on Safari-like browsers', () => {
    global.MediaRecorder = class {
      static isTypeSupported(type) {
        return type === 'audio/mp4'
      }
    }
    expect(pickMediaRecorderMimeType()).toBe('audio/mp4')
  })

  it('pickMediaRecorderMimeType returns empty when nothing supported', () => {
    global.MediaRecorder = class {
      static isTypeSupported() {
        return false
      }
    }
    expect(pickMediaRecorderMimeType()).toBe('')
  })

  it('createMediaRecorder passes mimeType when available', () => {
    let constructedWith = null
    global.MediaRecorder = class MockRecorder {
      constructor(stream, opts) {
        constructedWith = opts
        this.stream = stream
        this.mimeType = opts?.mimeType || ''
      }
      static isTypeSupported(type) {
        return type === 'audio/mp4'
      }
    }
    const stream = {}
    createMediaRecorder(stream)
    expect(constructedWith).toEqual({ mimeType: 'audio/mp4' })
  })
})
