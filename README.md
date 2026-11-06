# puto

Bot de Discord del server: se queda en el vc, aprende de los mensajes, juegos (`!puto adivina`, `!puto sexo`...), gifs y respuestas con IA (Gemini y Groq).

## Actualización automática

La VM revisa este repo cada 2 minutos (`actualizar.sh`, con un timer de systemd). Si hay un commit nuevo en `main`, lo baja, revisa que `bot.py` compile, lo copia a `/opt/vcbot/bot.py` y reinicia el servicio `vcbot`.

Las claves (Discord, Gemini, Groq), la base de mensajes y el lore **no** están en el repo: viven solo en `/opt/vcbot` en la VM.

## Memoria y respuestas de IA

La memoria sigue siendo **una sola para todo el servidor**, compartida entre canales de texto y voz.
Para responder, el bot elige recuerdos por coincidencias del tema, personas mencionadas y fecha, en lugar
de pasar conversaciones aleatorias. Busca palabras completas y reconoce tildes; todavía no es una búsqueda
semántica con embeddings. También incluye mensajes recientes y el mensaje exacto al que alguien responde,
aunque sea antiguo. Los ejemplos de tono del prompt son ilustrativos; no se guardan como recuerdos.

Esto es recuperación de contexto, no entrenamiento del modelo. Los borrados, ediciones y el comando para
olvidar personas se reflejan en la selección, sin mantener otra copia del historial.

## Modelos

Sin configurar nada nuevo, mantiene Gemini como principal y Groq como respaldo. En Groq prueba
`openai/gpt-oss-120b`, `openai/gpt-oss-20b` y `qwen/qwen3.8-27b`. Estos IDs figuran en el
[catálogo de Groq](https://console.groq.com/docs/models); la disponibilidad y las
[cuotas](https://console.groq.com/docs/rate-limits) dependen de la cuenta. No se activa facturación
ni se contrata otro servicio. Una clave asociada a una cuenta de pago sigue las condiciones de esa cuenta.

Podés cambiar la lista sin editar Python. Usá variables de entorno o archivos junto a `bot.py`, con los
modelos en orden separados por comas o espacios:

| Variable | Archivo | Uso |
| --- | --- | --- |
| `GROQ_MODELS` | `groq_models` | Modelos de Groq, incluidos Llama si tu cuenta aún los permite |
| `GEMINI_MODELS` | `gemini_models` | Modelos de Gemini para conversar |
| `GEMINI_LORE_MODELS` | `gemini_lore_models` | Modelos de Gemini para resumir el servidor |

Las variables tienen prioridad sobre los archivos. Después de cambiar la configuración de la VM,
reiniciá `vcbot`. Cambiar de modelo no garantiza más cuota: los límites también pueden ser compartidos.

## Usar un modelo propio, incluido uno entrenado

La conexión a [Ollama](https://docs.ollama.com/api/openai-compatibility) es opcional y está desactivada
por defecto. No hace falta para las mejoras de memoria. Si ya tenés Ollama en una máquina con capacidad
para el modelo, configurá junto a `bot.py`:

* `ollama_url`: `http://localhost:11434/v1` (o una URL privada accesible desde la VM).
* `ollama_model`: el nombre del modelo que ya instalaste en Ollama, por ejemplo `qwen3:8b` o `mi-bot`.

También sirven las variables `OLLAMA_BASE_URL` y `OLLAMA_MODEL`. Al activarlo, prueba el modelo local
primero; si falla, usa Gemini/Groq cuando haya claves configuradas. No expongas Ollama públicamente;
si vive en otra máquina, conectá ambas por una red privada. La memoria compartida se sigue usando.

Para entrenar un modelo propio, el siguiente paso es preparar **localmente** ejemplos revisados de
conversación y respuestas deseadas, apartando algunas conversaciones para evaluar el resultado.
No conviene entrenar con todo el historial sin revisar: las respuestas de personas no siempre son
respuestas adecuadas para el bot. Los datos y el modelo personalizado no se suben a este repositorio.

Se puede probar un ajuste LoRA/QLoRA de Qwen con los [notebooks de Unsloth](https://unsloth.ai/docs/get-started/unsloth-notebooks),
sujeto a la disponibilidad de GPU gratuita de Colab. Después hay que exportar el modelo a un formato
compatible e [importarlo en Ollama](https://docs.ollama.com/import), probarlo con las conversaciones
reservadas y poner su nombre en `ollama_model`. Entrenarlo gratis no proporciona alojamiento permanente:
la máquina que lo sirve necesita suficiente memoria y seguir encendida. Todavía no se entrenó ningún
modelo ni se comprobó el hardware de la VM.

## Comprobaciones offline

Con Python 3.12 y `discord.py` 2.7 instalado:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile bot.py
```

Las pruebas usan una base temporal en memoria y respuestas HTTP simuladas. No conectan con Discord
ni consumen llamadas a modelos de IA.
