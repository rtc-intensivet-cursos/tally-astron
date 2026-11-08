# Guarda as chaves no cofre (Secrets) do repositório rtc-intensivet-cursos/tally-astron.
# Lê dos arquivos do PC; nada aparece na tela.
$gh = 'C:\Program Files\GitHub CLI\gh.exe'
$repo = 'rtc-intensivet-cursos/tally-astron'

function Ler($arquivo, $nome) {
    $linha = Get-Content $arquivo | Where-Object { $_ -like "$nome=*" } | Select-Object -First 1
    if (-not $linha) { throw "Não achei $nome em $arquivo" }
    $v = $linha.Substring($nome.Length + 1).Trim()
    if ($v -like '*COLE_AQUI*') { throw "Preencha $nome em $arquivo primeiro" }
    return $v
}

Ler 'C:\astron-mcp\astron.env' 'ASTRON_AM_KEY'    | & $gh secret set ASTRON_AM_KEY    -R $repo
Ler 'C:\astron-mcp\astron.env' 'ASTRON_AM_SECRET' | & $gh secret set ASTRON_AM_SECRET -R $repo
Ler 'C:\tally-astron\.env'     'TALLY_API_KEY'    | & $gh secret set TALLY_API_KEY    -R $repo

& $gh secret list -R $repo
Write-Host "Pronto: chaves guardadas no GitHub." -ForegroundColor Green
