param([string]$Deck, [string]$OutDir)
$app = New-Object -ComObject PowerPoint.Application
try {
  $p = $app.Presentations.Open($Deck, -1, 0, 0)
  $i = 0
  foreach ($s in $p.Slides) { $i++; $s.Export((Join-Path $OutDir ("s{0:D2}.png" -f $i)), "PNG", 800, 450) }
  $p.Close()
  "exported $i"
} finally { $app.Quit() }
