param([string]$Doc, [string]$Pdf)
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open($Doc, $false, $false)
  foreach ($f in $d.Fields) { if ($f.Type -eq 12) { $f.Update() | Out-Null } }
  $d.Fields.Update() | Out-Null
  foreach ($t in $d.TablesOfContents) { $t.Update() | Out-Null }
  $d.Repaginate()
  foreach ($t in $d.TablesOfContents) { $t.UpdatePageNumbers() | Out-Null }
  $d.Save()
  $d.ExportAsFixedFormat($Pdf, 17)
  "pages: " + $d.ComputeStatistics(2)
  $d.Close($false)
} finally { $w.Quit() }
