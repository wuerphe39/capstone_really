param(
    [Parameter(Mandatory=$true)][string]$TextPath,
    [Parameter(Mandatory=$true)][string]$WavePath
)

Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $speaker.SelectVoice('Microsoft Heami Desktop')
    $speaker.Rate = 0
    $speaker.SetOutputToWaveFile($WavePath)
    $speaker.Speak([System.IO.File]::ReadAllText($TextPath, [System.Text.Encoding]::UTF8))
} finally {
    $speaker.Dispose()
}
