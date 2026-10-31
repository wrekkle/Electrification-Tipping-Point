$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path
$path = Join-Path $root 'paper\draft\Electrification_tipping_point_v2_draft_2026-10-30.docx'
try { $word = New-Object -ComObject Word.Application } catch { Write-Output 'WORD_NOT_AVAILABLE'; exit 0 }
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($path, $false, $true)
  Write-Output ("pages=" + $doc.ComputeStatistics(2) + " words=" + $doc.ComputeStatistics(0) + " paragraphs=" + $doc.Paragraphs.Count + " tables=" + $doc.Tables.Count + " omaths=" + $doc.OMaths.Count)
  $anchors = @(
    @{ k='eq13'; t='Charging failure is the case in which an EV that wants to charge' },
    @{ k='eq14'; t='Parking failure is the case in which an ICEV finds no admissible ordinary berth' },
    @{ k='eq15'; t='The effect of one stretch of occupancy is defined as the difference' })
  $n = $doc.Paragraphs.Count
  for ($i = 1; $i -le $n; $i++) {
    $t = $doc.Paragraphs.Item($i).Range.Text
    foreach ($a in $anchors) {
      if ($t.StartsWith($a.t)) {
        $eqp = $doc.Paragraphs.Item($i + 1)
        Write-Output ("{0}: lines={1} page={2} text={3}" -f $a.k, $eqp.Range.ComputeStatistics(1), $eqp.Range.Information(3), $eqp.Range.Text.Replace([char]13, ' ').Trim())
      }
    }
  }
  $doc.Close($false)
} catch { Write-Output ("WORD_ERROR: " + $_.Exception.Message) } finally { $word.Quit() }
