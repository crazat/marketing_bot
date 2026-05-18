export async function copyTextToClipboard(text: string): Promise<void> {
  if (
    typeof window !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    window.isSecureContext &&
    typeof navigator.clipboard?.writeText === 'function'
  ) {
    await navigator.clipboard.writeText(text)
    return
  }

  if (typeof document === 'undefined') {
    throw new Error('Clipboard is unavailable')
  }

  const textArea = document.createElement('textarea')
  textArea.value = text
  textArea.setAttribute('readonly', '')
  textArea.style.position = 'fixed'
  textArea.style.top = '0'
  textArea.style.left = '-9999px'
  textArea.style.opacity = '0'

  document.body.appendChild(textArea)
  try {
    textArea.focus()
    textArea.select()
    textArea.setSelectionRange(0, textArea.value.length)

    const copied = document.execCommand('copy')
    if (!copied) {
      throw new Error('Clipboard copy failed')
    }
  } finally {
    document.body.removeChild(textArea)
  }
}
