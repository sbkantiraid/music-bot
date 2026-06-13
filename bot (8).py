import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
import subprocess
from dotenv import load_dotenv
from collections import deque

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ─── Instalar FFmpeg automáticamente si no está disponible ────────────────────
def ensure_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("✅ FFmpeg encontrado.")
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("⚙️ FFmpeg no encontrado, instalando...")
        os.system("apt-get update -qq && apt-get install -y ffmpeg")
        print("✅ FFmpeg instalado.")

ensure_ffmpeg()

# ─── Configuración de yt-dlp ───────────────────────────────────────────────────

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": "in_playlist",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

FFMPEG_EXECUTABLE = "ffmpeg"  # cambia a "/usr/bin/ffmpeg" si sigue fallando

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


# ─── Estado por servidor ───────────────────────────────────────────────────────

class GuildState:
    def __init__(self):
        self.queue: deque = deque()
        self.current: dict | None = None
        self.loop: bool = False
        self.loop_queue: bool = False
        self.volume: float = 0.5

    def clear(self):
        self.queue.clear()
        self.current = None


# ─── Bot ───────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True      # necesario para detectar canales de voz
intents.members = True           # necesario para ver en qué VC está cada miembro

bot = commands.Bot(command_prefix="!", intents=intents)
states: dict[int, GuildState] = {}


def get_state(guild_id: int) -> GuildState:
    if guild_id not in states:
        states[guild_id] = GuildState()
    return states[guild_id]


# ─── Helper: conectar al VC del usuario ───────────────────────────────────────

async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient | None:
    """
    Conecta el bot al canal de voz del usuario.
    - Si el usuario NO está en un VC → avisa y devuelve None.
    - Si el bot ya está en el mismo VC → devuelve el VoiceClient existente.
    - Si el bot está en otro VC → se mueve al canal del usuario.
    - Si el bot no está en ningún VC → se conecta.
    """
    member_vc = ctx.author.voice

    if not member_vc or not member_vc.channel:
        await ctx.send("❌ Tienes que estar en un canal de voz primero.")
        return None

    channel = member_vc.channel
    vc: discord.VoiceClient | None = ctx.voice_client

    if vc:
        if vc.channel != channel:
            await vc.move_to(channel)
            await ctx.send(f"🔊 Me moví a **{channel.name}**")
    else:
        vc = await channel.connect()
        await ctx.send(f"🔊 Conectado a **{channel.name}**")

    return vc


# ─── Helpers de audio ─────────────────────────────────────────────────────────

async def fetch_track(query: str) -> list[dict]:
    loop = asyncio.get_event_loop()

    def _extract():
        data = ytdl.extract_info(query, download=False)
        if data is None:
            return []
        if "entries" in data:
            tracks = []
            for entry in data["entries"]:
                if entry:
                    tracks.append({
                        "title": entry.get("title", "Desconocido"),
                        "url": entry.get("url") or entry.get("webpage_url"),
                        "webpage_url": entry.get("webpage_url", ""),
                        "duration": entry.get("duration", 0),
                        "thumbnail": entry.get("thumbnail", ""),
                        "uploader": entry.get("uploader", ""),
                    })
            return tracks
        return [{
            "title": data.get("title", "Desconocido"),
            "url": data.get("url"),
            "webpage_url": data.get("webpage_url", ""),
            "duration": data.get("duration", 0),
            "thumbnail": data.get("thumbnail", ""),
            "uploader": data.get("uploader", ""),
        }]

    return await loop.run_in_executor(None, _extract)


async def resolve_stream_url(track: dict) -> str:
    if track.get("webpage_url"):
        loop = asyncio.get_event_loop()
        def _get():
            opts = {**YTDL_OPTIONS, "extract_flat": False}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(track["webpage_url"], download=False)
                return info["url"]
        return await loop.run_in_executor(None, _get)
    return track["url"]


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


async def play_next(guild: discord.Guild):
    state = get_state(guild.id)
    vc: discord.VoiceClient | None = guild.voice_client

    if not vc or not vc.is_connected():
        return

    if state.loop and state.current:
        track = state.current
    elif state.queue:
        track = state.queue.popleft()
        if state.loop_queue:
            state.queue.append(track)
        state.current = track
    else:
        state.current = None
        return

    try:
        stream_url = await resolve_stream_url(track)
    except Exception as e:
        print(f"Error obteniendo stream: {e}")
        await play_next(guild)
        return

    source = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_EXECUTABLE, **FFMPEG_OPTIONS),
        volume=state.volume,
    )

    def after_play(error):
        if error:
            print(f"Error de reproducción: {error}")
        asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)

    vc.play(source, after=after_play)


# ─── Eventos ──────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="!play | /play"
    ))
    print(f"✅  Bot conectado como {bot.user}")


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Desconecta el bot si se queda solo en el canal de voz."""
    vc = member.guild.voice_client
    if not vc:
        return
    # Comprobar si el bot se quedó solo
    if len(vc.channel.members) == 1 and vc.channel.members[0] == member.guild.me:
        state = get_state(member.guild.id)
        state.clear()
        await vc.disconnect()


# ─── Comandos ─────────────────────────────────────────────────────────────────

@bot.command(name="join", aliases=["conectar"])
async def join(ctx: commands.Context):
    """Entra al canal de voz del usuario."""
    await ensure_voice(ctx)


@bot.command(name="play", aliases=["p", "reproducir"])
async def play(ctx: commands.Context, *, query: str):
    """Reproduce una canción o playlist (URL o búsqueda)."""
    vc = await ensure_voice(ctx)
    if not vc:
        return  # el usuario no estaba en un VC, ya se avisó

    state = get_state(ctx.guild.id)

    async with ctx.typing():
        tracks = await fetch_track(query)

    if not tracks:
        return await ctx.send("❌ No encontré nada con esa búsqueda.")

    if len(tracks) == 1:
        state.queue.append(tracks[0])
        embed = discord.Embed(
            title="➕ Añadido a la cola",
            description=f"[{tracks[0]['title']}]({tracks[0]['webpage_url']})",
            color=0x1DB954,
        )
        embed.set_thumbnail(url=tracks[0]["thumbnail"])
        embed.add_field(name="Duración", value=format_duration(tracks[0]["duration"]))
        await ctx.send(embed=embed)
    else:
        for t in tracks:
            state.queue.append(t)
        embed = discord.Embed(
            title="📋 Playlist añadida",
            description=f"**{len(tracks)} canciones** en cola",
            color=0x1DB954,
        )
        await ctx.send(embed=embed)

    if not vc.is_playing() and not vc.is_paused():
        await play_next(ctx.guild)


@bot.command(name="skip", aliases=["s", "siguiente"])
async def skip(ctx: commands.Context):
    """Salta la canción actual."""
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("⏭ Canción saltada.")
    else:
        await ctx.send("❌ No hay ninguna canción reproduciéndose.")


@bot.command(name="pause", aliases=["pausa"])
async def pause(ctx: commands.Context):
    """Pausa la reproducción."""
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("⏸ Pausado.")
    else:
        await ctx.send("❌ No hay nada reproduciéndose.")


@bot.command(name="resume", aliases=["continuar", "reanudar"])
async def resume(ctx: commands.Context):
    """Reanuda la reproducción."""
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("▶️ Reanudado.")
    else:
        await ctx.send("❌ No hay nada pausado.")


@bot.command(name="stop", aliases=["parar"])
async def stop(ctx: commands.Context):
    """Para la música y vacía la cola."""
    state = get_state(ctx.guild.id)
    state.clear()
    vc = ctx.voice_client
    if vc:
        vc.stop()
    await ctx.send("⏹ Música parada y cola vaciada.")


@bot.command(name="queue", aliases=["q", "cola", "lista"])
async def queue_cmd(ctx: commands.Context):
    """Muestra la cola de canciones."""
    state = get_state(ctx.guild.id)
    if not state.current and not state.queue:
        return await ctx.send("📭 La cola está vacía.")

    lines = []
    if state.current:
        lines.append(f"▶️ **Ahora:** {state.current['title']} `{format_duration(state.current['duration'])}`")

    for i, track in enumerate(list(state.queue)[:15], 1):
        lines.append(f"`{i}.` {track['title']} `{format_duration(track['duration'])}`")

    remaining = len(state.queue) - 15
    if remaining > 0:
        lines.append(f"*… y {remaining} canciones más*")

    embed = discord.Embed(
        title="🎵 Cola de reproducción",
        description="\n".join(lines),
        color=0x1DB954,
    )
    loop_status = "🔂 Canción" if state.loop else ("🔁 Cola" if state.loop_queue else "desactivado")
    embed.set_footer(text=f"Bucle: {loop_status} • Volumen: {int(state.volume * 100)}%")
    await ctx.send(embed=embed)


@bot.command(name="nowplaying", aliases=["np", "ahora"])
async def nowplaying(ctx: commands.Context):
    """Muestra la canción actual."""
    state = get_state(ctx.guild.id)
    if not state.current:
        return await ctx.send("❌ No se está reproduciendo nada.")
    t = state.current
    embed = discord.Embed(
        title="🎶 Reproduciendo ahora",
        description=f"[{t['title']}]({t['webpage_url']})",
        color=0x1DB954,
    )
    embed.set_thumbnail(url=t["thumbnail"])
    embed.add_field(name="Duración", value=format_duration(t["duration"]))
    embed.add_field(name="Subido por", value=t["uploader"] or "?")
    await ctx.send(embed=embed)


@bot.command(name="volume", aliases=["vol", "volumen"])
async def volume(ctx: commands.Context, vol: int):
    """Ajusta el volumen (0-100)."""
    if not 0 <= vol <= 100:
        return await ctx.send("❌ El volumen debe estar entre 0 y 100.")
    state = get_state(ctx.guild.id)
    state.volume = vol / 100
    vc = ctx.voice_client
    if vc and vc.source:
        vc.source.volume = state.volume
    await ctx.send(f"🔊 Volumen: **{vol}%**")


@bot.command(name="loop", aliases=["bucle"])
async def loop_cmd(ctx: commands.Context, mode: str = "song"):
    """Activa el bucle. Modos: song, queue, off"""
    state = get_state(ctx.guild.id)
    mode = mode.lower()
    if mode in ("song", "cancion", "canción"):
        state.loop = True
        state.loop_queue = False
        await ctx.send("🔂 Bucle de canción activado.")
    elif mode in ("queue", "cola"):
        state.loop = False
        state.loop_queue = True
        await ctx.send("🔁 Bucle de cola activado.")
    elif mode in ("off", "no", "apagar"):
        state.loop = False
        state.loop_queue = False
        await ctx.send("➡️ Bucle desactivado.")
    else:
        await ctx.send("❌ Modo inválido. Usa: `song`, `queue` o `off`.")


@bot.command(name="remove", aliases=["eliminar", "quitar"])
async def remove(ctx: commands.Context, index: int):
    """Elimina una canción de la cola por su número."""
    state = get_state(ctx.guild.id)
    if index < 1 or index > len(state.queue):
        return await ctx.send("❌ Número de canción inválido.")
    queue_list = list(state.queue)
    removed = queue_list.pop(index - 1)
    state.queue = deque(queue_list)
    await ctx.send(f"🗑 Eliminado: **{removed['title']}**")


@bot.command(name="clear", aliases=["vaciar", "limpiar"])
async def clear(ctx: commands.Context):
    """Vacía la cola (sin parar la canción actual)."""
    state = get_state(ctx.guild.id)
    state.queue.clear()
    await ctx.send("🧹 Cola vaciada.")


@bot.command(name="shuffle", aliases=["mezclar", "aleatorio"])
async def shuffle(ctx: commands.Context):
    """Mezcla la cola de forma aleatoria."""
    import random
    state = get_state(ctx.guild.id)
    if len(state.queue) < 2:
        return await ctx.send("❌ Necesitas al menos 2 canciones en la cola.")
    queue_list = list(state.queue)
    random.shuffle(queue_list)
    state.queue = deque(queue_list)
    await ctx.send("🔀 Cola mezclada aleatoriamente.")


@bot.command(name="leave", aliases=["dc", "salir", "desconectar"])
async def leave(ctx: commands.Context):
    """Desconecta el bot del canal de voz."""
    state = get_state(ctx.guild.id)
    state.clear()
    vc = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("👋 Desconectado.")
    else:
        await ctx.send("❌ No estoy en ningún canal de voz.")


@bot.command(name="move", aliases=["mover"])
async def move(ctx: commands.Context, origin: int, destination: int):
    """Mueve una canción de una posición a otra en la cola."""
    state = get_state(ctx.guild.id)
    q = list(state.queue)
    if not (1 <= origin <= len(q) and 1 <= destination <= len(q)):
        return await ctx.send("❌ Posiciones inválidas.")
    track = q.pop(origin - 1)
    q.insert(destination - 1, track)
    state.queue = deque(q)
    await ctx.send(f"↕️ **{track['title']}** movido a la posición **{destination}**.")


# ─── Slash commands ───────────────────────────────────────────────────────────

@bot.tree.command(name="play", description="Reproduce una canción o playlist")
@app_commands.describe(query="URL o nombre de la canción / playlist")
async def slash_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    member_vc = interaction.user.voice
    if not member_vc or not member_vc.channel:
        return await interaction.followup.send("❌ Tienes que estar en un canal de voz primero.")

    channel = member_vc.channel
    vc = interaction.guild.voice_client

    if vc:
        if vc.channel != channel:
            await vc.move_to(channel)
    else:
        vc = await channel.connect()

    state = get_state(interaction.guild_id)
    tracks = await fetch_track(query)

    if not tracks:
        return await interaction.followup.send("❌ No encontré nada.")

    for t in tracks:
        state.queue.append(t)

    msg = f"➕ **{tracks[0]['title']}** añadida." if len(tracks) == 1 else f"📋 **{len(tracks)} canciones** añadidas."
    await interaction.followup.send(msg)

    if not vc.is_playing() and not vc.is_paused():
        await play_next(interaction.guild)


@bot.tree.command(name="skip", description="Salta la canción actual")
async def slash_skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭ Canción saltada.")
    else:
        await interaction.response.send_message("❌ No hay nada reproduciéndose.")


@bot.tree.command(name="queue", description="Muestra la cola de canciones")
async def slash_queue(interaction: discord.Interaction):
    state = get_state(interaction.guild_id)
    if not state.current and not state.queue:
        return await interaction.response.send_message("📭 La cola está vacía.")
    lines = []
    if state.current:
        lines.append(f"▶️ **Ahora:** {state.current['title']}")
    for i, t in enumerate(list(state.queue)[:10], 1):
        lines.append(f"`{i}.` {t['title']}")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="stop", description="Para la música y vacía la cola")
async def slash_stop(interaction: discord.Interaction):
    state = get_state(interaction.guild_id)
    state.clear()
    vc = interaction.guild.voice_client
    if vc:
        vc.stop()
    await interaction.response.send_message("⏹ Música parada.")


@bot.tree.command(name="leave", description="Desconecta el bot")
async def slash_leave(interaction: discord.Interaction):
    state = get_state(interaction.guild_id)
    state.clear()
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("👋 Hasta luego.")
    else:
        await interaction.response.send_message("❌ No estoy en un canal de voz.")


# ─── Arranque ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("Falta DISCORD_TOKEN en el fichero .env")
    bot.run(TOKEN)