# puto

Bot de Discord del server: se queda en el vc, aprende de los mensajes, juegos (`!puto adivina`, `!puto sexo`...), gifs y respuestas con IA (Gemini y Groq).

## Actualización automática

La VM revisa este repo cada 2 minutos (`actualizar.sh`, con un timer de systemd). Si hay un commit nuevo en `main`, lo baja, revisa que `bot.py` compile, lo copia a `/opt/vcbot/bot.py` y reinicia el servicio `vcbot`.

Las claves (Discord, Gemini, Groq), la base de mensajes y el lore **no** están en el repo: viven solo en `/opt/vcbot` en la VM.
