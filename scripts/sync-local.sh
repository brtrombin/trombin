#!/usr/bin/env bash
# Sync do Substack rodando neste computador — uso: npm run sync
#
# Faz o que o workflow do GitHub fazia (lá o Substack bloqueia o acesso):
#   1. prepara um ambiente Python só do projeto (.venv-sync), na primeira vez
#   2. roda scripts/sync-substack.py
#   3. se entraram posts novos, faz commit só desses arquivos e dá push
#      (o push na main dispara o deploy do site)
set -euo pipefail

# sempre a partir da raiz do repositório, não importa de onde foi chamado
cd "$(dirname "$0")/.."

VENV=".venv-sync"
STAMP="$VENV/.instalado"

# ── 1. Ambiente Python ───────────────────────────────────────────────────────
if [ ! -x "$VENV/bin/python" ]; then
  echo "Criando ambiente Python em $VENV ..."
  python3 -m venv "$VENV"
fi

# instala as dependências na primeira vez e sempre que requirements-sync.txt mudar
if [ ! -f "$STAMP" ] || [ requirements-sync.txt -nt "$STAMP" ]; then
  echo "Instalando dependências ..."
  "$VENV/bin/pip" install --quiet --disable-pip-version-check -r requirements-sync.txt
  touch "$STAMP"
fi

# ── 2. Importação ────────────────────────────────────────────────────────────
# Lista de arquivos ainda não versionados em articles/ e img/, antes e depois:
# a diferença são exatamente os arquivos que o sync criou.
untracked() { git ls-files --others --exclude-standard -- articles img | sort; }

before="$(untracked)"
# -W: silencia o aviso de OpenSSL do urllib3 no Python do macOS
"$VENV/bin/python" -W "ignore:::urllib3" scripts/sync-substack.py
after="$(untracked)"

new_files=()
while IFS= read -r file; do
  [ -n "$file" ] && new_files+=("$file")
done < <(comm -13 <(printf '%s\n' "$before") <(printf '%s\n' "$after"))

# ── 3. Commit e push ─────────────────────────────────────────────────────────
if [ "${#new_files[@]}" -eq 0 ]; then
  echo "Nenhum post novo: nada para enviar."
  exit 0
fi

echo "Arquivos novos:"
printf '  %s\n' "${new_files[@]}"

# o commit leva só os arquivos do sync — outras alterações em andamento
# na pasta ficam de fora
git add -- "${new_files[@]}"
git commit --quiet -m "sync: importa novos textos do Substack" -- "${new_files[@]}"
git push
echo "Enviado. O deploy do site começa em seguida."
