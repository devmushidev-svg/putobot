#!/bin/bash
# Lo corre la VM cada 2 minutos (putobot-actualizar.timer): si hay cambios en GitHub, los baja,
# revisa que bot.py no tenga errores, lo copia a /opt/vcbot y reinicia el bot.
set -e
REPO=/opt/vcbot/repo
cd "$REPO"
git fetch -q origin main
if [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ]; then
  exit 0
fi
git reset -q --hard origin/main
if python3 -m py_compile bot.py; then
  cat bot.py > /opt/vcbot/bot.py
  systemctl restart vcbot
  echo "bot actualizado a $(git rev-parse --short HEAD): $(git log -1 --format=%s)"
else
  echo "bot.py nuevo tiene errores, no lo instalé"
  exit 1
fi
