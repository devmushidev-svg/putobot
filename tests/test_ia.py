"""Pruebas offline: python -m unittest discover -s tests -v (requiere discord.py)."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

import bot


class RecuerdosTests(unittest.TestCase):
    def setUp(self):
        self.brain = bot.Brain(":memory:")

    def tearDown(self):
        self.brain.db.close()

    def aprender(self, mid, autor, texto, canal=10, guild=1):
        self.brain.learn(mid, guild, canal, autor, texto)

    def test_prioriza_tema_y_persona_sin_aislar_canales(self):
        self.aprender(1, 20, "juego fútbol con lucas", canal=10)
        self.aprender(2, 30, "juego fútbol cada martes", canal=11)
        self.aprender(3, 20, "hoy estoy cocinando pasta", canal=12)
        self.aprender(4, 20, "juego fútbol en otro servidor", guild=2)
        recientes, relevantes = self.brain.recuerdos_ia(1, "qué sabes del futbol", (20,), 35)
        self.assertEqual(relevantes[0], (20, "juego fútbol con lucas"))
        self.assertIn((30, "juego fútbol cada martes"), relevantes)
        self.assertIn((20, "hoy estoy cocinando pasta"), relevantes)
        self.assertNotIn((20, "juego fútbol en otro servidor"), recientes + relevantes)
        self.assertEqual(self.brain.db.execute("SELECT DISTINCT channel_id FROM messages").fetchall(), [(bot.SHARED,)])

    def test_desempata_por_recencia_y_no_por_azar(self):
        self.aprender(1, 20, "partida antigua de ajedrez")
        self.aprender(2, 30, "partida nueva de ajedrez")
        primero = self.brain.recuerdos_ia(1, "ajedrez", (), 35)
        self.assertEqual(primero[1][0][0], 30)
        self.assertEqual(primero, self.brain.recuerdos_ia(1, "ajedrez", (), 35))

    def test_no_confunde_subcadenas_y_deduplica_por_autor(self):
        self.aprender(1, 20, "me gusta jugar futbol")
        self.aprender(2, 20, "me gusta jugar futbol")
        self.aprender(3, 30, "me gusta jugar futbol")
        self.aprender(4, 40, "el futbolista llego temprano")
        _, relevantes = self.brain.recuerdos_ia(1, "futbol", (), 35)
        self.assertEqual(len(relevantes), 2)
        self.assertEqual({uid for uid, _ in relevantes}, {20, 30})

    def test_olvidos_y_ediciones_se_reflejan_sin_copia_residual(self):
        self.aprender(1, 20, "estoy jugando ajedrez")
        self.aprender(2, 30, "estoy jugando ajedrez")
        self.brain.forget_user(1, 20)
        self.brain.learn(2, 1, 10, 30, "estoy jugando futbol", revision=1)
        self.assertEqual(self.brain.recuerdos_ia(1, "ajedrez", (), 35)[1], [])
        self.assertEqual(len(self.brain.recuerdos_ia(1, "futbol", (), 35)[1]), 1)
        self.brain.forget_message(2)
        self.assertEqual(self.brain.recuerdos_ia(1, "futbol", (), 35), ([], []))

    def test_sin_datos_relacionados_solo_devuelve_recientes(self):
        self.aprender(1, 20, "hoy comemos pizza")
        recientes, relevantes = self.brain.recuerdos_ia(1, "astronomia", (), 35)
        self.assertTrue(recientes)
        self.assertEqual(relevantes, [])


def mensaje(guild, canal, uid, contenido, mid=50, referencia=None):
    m = object.__new__(discord.Message)
    m.id, m.guild, m.channel = mid, guild, canal
    m.author = SimpleNamespace(id=uid, display_name=f"persona {uid}")
    m.content, m.reference, m.mentions, m.webhook_id = contenido, referencia, [], None
    return m


class RespuestaHTTP:
    def __init__(self, status, datos=None):
        self.status, self.datos = status, datos

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.datos

    async def text(self):
        return "not found" if self.status == 404 else "rate limit"


class ClienteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = bot.create_client(bot.Config(token="offline", voice_channel_id=1))
        self.client._connection.user = SimpleNamespace(id=999)
        self.guild = SimpleNamespace(id=1)
        self.canal = SimpleNamespace(id=10, guild=self.guild)

    async def asyncTearDown(self):
        self.client.worker.executor.shutdown(wait=True)

    def referencia(self, mid=5):
        r = discord.MessageReference(message_id=mid, channel_id=self.canal.id, guild_id=self.guild.id)
        r._state = self.client._connection
        return r

    async def test_respuesta_antigua_fuera_del_historial_se_incluye_y_se_busca(self):
        antiguo = mensaje(self.guild, self.canal, 999, "te recomiendo jugar ajedrez", mid=5)
        self.canal.fetch_message = AsyncMock(return_value=antiguo)
        actual = mensaje(self.guild, self.canal, 20, "por qué ese juego?", referencia=self.referencia())
        self.client.ultimos_mensajes = AsyncMock(return_value="persona 30: hola")
        self.client.proveedores_ia = Mock(return_value=[("groq", "offline", "falsa", ["modelo"], 35)])
        self.client.contexto_server = AsyncMock(return_value=([], []))
        capturado = []

        async def generar(guild, armar, **kw):
            capturado.extend(armar(35))
            return "porque te gusta pensar"

        self.client.ia_natural = generar
        await self.client.ia_responder(actual)
        self.assertIn("Mensaje exacto al que responde", capturado[-1]["content"])
        self.assertIn(antiguo.content, capturado[-1]["content"])
        self.assertIn("ajedrez", self.client.contexto_server.call_args.args[1])
        # Resolver de nuevo el mismo reply usa el resultado; no vuelve a pedirlo a Discord.
        self.assertIs(await self.client.mensaje_referenciado(actual), antiguo)
        self.canal.fetch_message.assert_awaited_once_with(5)

    async def test_reply_borrado_no_hace_fallar_la_conversacion(self):
        referencia = self.referencia()
        referencia.resolved = discord.DeletedReferencedMessage(referencia)
        actual = mensaje(self.guild, self.canal, 20, "hola", referencia=referencia)
        self.assertIsNone(await self.client.mensaje_referenciado(actual))

    async def test_reply_inaccesible_o_timeout_no_bloquea(self):
        self.canal.fetch_message = AsyncMock(side_effect=asyncio.TimeoutError)
        actual = mensaje(self.guild, self.canal, 20, "hola", referencia=self.referencia())
        self.assertIsNone(await self.client.mensaje_referenciado(actual))

    async def test_apodos_y_menciones_priorizan_personas_correctas(self):
        self.client.pool_nombres[1] = {"lucas": 30, "ana": 40}
        actual = mensaje(self.guild, self.canal, 20, "qué juega lucas con manada?")
        actual.mentions = [SimpleNamespace(id=50), SimpleNamespace(id=999)]
        self.assertEqual(self.client.personas_ia(actual, actual.content), (30, 50))

    async def test_respuesta_larga_se_acorta_sin_otra_consulta(self):
        largo = ("no te odio solo me da risa hablar con vos cuando venís a jugar y después "
                 "te vas a otro canal para contar lo mismo otra vez mientras todos seguimos jugando")
        self.client.ia = AsyncMock(return_value=largo)
        armar = lambda n: [{"role": "system", "content": bot.PERSONALIDAD},
                          {"role": "user", "content": "me odias?"}]
        salida = await self.client.ia_natural(self.guild, armar)
        self.assertLessEqual(len(salida.split()), 20)
        self.assertLessEqual(len(salida), 160)
        self.client.ia.assert_awaited_once()
        self.assertEqual(self.client.ia.call_args.kwargs["max_tokens"], 64)
        instruccion = self.client.ia.call_args.args[0](35)[0]["content"]
        self.assertIn("como máximo 20 palabras", instruccion)

    async def test_imitacion_larga_tambien_se_limita(self):
        self.client.proveedores_ia = Mock(return_value=[("groq", "offline", "falsa", ["modelo"], 35)])
        self.client.worker.call = AsyncMock(return_value=["un mensaje de ejemplo"] * 6)
        self.client.ia = AsyncMock(return_value="HOLA " + "texto " * 100)
        salida = await self.client.ia_imitar(self.guild, SimpleNamespace(id=20, display_name="persona"))
        self.assertTrue(salida.startswith("HOLA "))
        self.assertLessEqual(len(salida.split()), 20)
        self.assertLessEqual(len(salida), 160)
        self.client.ia.assert_awaited_once()

    async def test_contexto_respeta_cupo_incluso_con_duplicados(self):
        recientes = [f"persona: reciente {n}" for n in range(20)]
        tema = [recientes[-1]] + [f"persona: tema {n}" for n in range(60)]
        for cupo in (1, 2, 3, 35):
            texto = self.client.armar_contexto(recientes, tema, cupo)
            mensajes = [linea for linea in texto.splitlines() if linea.startswith("persona:")]
            self.assertEqual(len(mensajes), cupo)
            self.assertEqual(len(mensajes), len(set(mensajes)))

    async def test_modelos_configurables_y_ollama_solo_si_se_activa(self):
        config = {"GROQ_API_KEY": "falsa", "GROQ_MODELS": "modelo-a, modelo-b modelo-a"}
        self.client._leer_clave = lambda variable, archivo: config.get(variable, "")
        proveedores = self.client.proveedores_ia()
        self.assertEqual([p[0] for p in proveedores], ["groq"])
        self.assertEqual(proveedores[0][3], ["modelo-a", "modelo-b"])
        config["GROQ_MODELS"] = " ,  , "
        self.assertEqual(self.client.proveedores_ia()[0][3], bot.GROQ_MODELOS)
        config.update(OLLAMA_BASE_URL="http://localhost:11434/v1/", OLLAMA_MODEL="mi-bot-entrenado")
        local = self.client.proveedores_ia()[0]
        self.assertEqual(local[0], "ollama")
        self.assertEqual(local[1], "http://localhost:11434/v1/chat/completions")
        self.assertEqual(local[3], ["mi-bot-entrenado"])

    async def test_modelo_no_disponible_pasa_al_respaldo_sin_repetirlo(self):
        self.client.proveedores_ia = Mock(return_value=[
            ("groq", "offline", "falsa", bot.GROQ_MODELOS[:2], 35)])
        datos = {"choices": [{"message": {"content": "bot: respuesta de respaldo"}}]}
        post = Mock(side_effect=[RespuestaHTTP(404), RespuestaHTTP(200, datos), RespuestaHTTP(200, datos)])
        self.client.sesion = SimpleNamespace(closed=False, post=post)
        armar = lambda n: [{"role": "user", "content": "hola"}]
        self.assertEqual(await self.client.ia(armar), "respuesta de respaldo")
        self.assertEqual(await self.client.ia(armar), "respuesta de respaldo")
        modelos = [llamada.kwargs["json"]["model"] for llamada in post.call_args_list]
        self.assertEqual(modelos, [bot.GROQ_MODELOS[0], bot.GROQ_MODELOS[1], bot.GROQ_MODELOS[1]])
        self.assertFalse(post.call_args.kwargs["json"]["include_reasoning"])

    async def test_cuota_de_un_proveedor_no_bloquea_otro_con_mismo_nombre_de_modelo(self):
        self.client.proveedores_ia = Mock(return_value=[
            ("primero", "offline-a", "falsa", ["modelo"], 35),
            ("segundo", "offline-b", "falsa", ["modelo"], 35)])
        datos = {"choices": [{"message": {"content": "funciona"}}]}
        post = Mock(side_effect=[RespuestaHTTP(429), RespuestaHTTP(200, datos)])
        self.client.sesion = SimpleNamespace(closed=False, post=post)
        self.assertEqual(await self.client.ia(lambda n: [{"role": "user", "content": "hola"}]), "funciona")
        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
