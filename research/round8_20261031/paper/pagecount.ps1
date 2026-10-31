
$ErrorActionPreference = 'Stop'
$files = @(
  @{ src = 'C:\Projects\停车场充电桩优化方案\research\round8_20261031\paper\Electrification_tipping_point_v2_draft_rev5.docx'; pdf = 'C:\Projects\停车场充电桩优化方案\research\round8_20261031\paper\rev5_main_skeleton.pdf' },
  @{ src = 'C:\Projects\停车场充电桩优化方案\research\round8_20261031\paper\Electrification_tipping_point_v2_supplementary_rev5.docx'; pdf = 'C:\Projects\停车场充电桩优化方案\research\round8_20261031\paper\rev5_si_skeleton.pdf' }
)
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  foreach ($f in $files) {
    $doc = $word.Documents.Open($f.src, $false, $true)
    $doc.Repaginate()
    $pages = $doc.ComputeStatistics(2)
    $words = $doc.ComputeStatistics(0)
    $doc.ExportAsFixedFormat($f.pdf, 17)
    $doc.Close($false)
    Write-Output ("{0} pages={1} word_stat={2}" -f (Split-Path $f.src -Leaf), $pages, $words)
  }
} finally {
  $word.Quit()
}
