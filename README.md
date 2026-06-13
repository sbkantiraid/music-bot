# 🎵 Music Bot

Un bot de Discord para reproducir música desde YouTube con soporte para playlists, bucles, control de volumen y más.

## 🚀 Características

- ▶️ Reproducir canciones y playlists de YouTube
- ⏭️ Skip, pausa y reanuda
- 🔂 Bucles por canción o cola
- 🎚️ Control de volumen
- 📋 Cola de canciones
- 🔀 Mezcla aleatoria
- 📱 Comandos slash y prefijo

## 📋 Requisitos

- Python 3.10+
- FFmpeg instalado
- Bot de Discord con permisos de:
  - Connect (conectarse a canales de voz)
  - Speak (hablar en canales de voz)

## ⚙️ Instalación Local

```bash
# Clonar repositorio
git clone https://github.com/sbkantiraid/music-bot.git
cd music-bot

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Crear archivo .env
cp .env.example .env
# Editar .env con tu DISCORD_TOKEN

# Ejecutar bot
python bot.py
```

## 🚄 Despliegue en Railway

### Paso 1: Conectar repositorio a Railway

1. Ve a [railway.app](https://railway.app)
2. Login con GitHub
3. Crea un nuevo proyecto
4. Conecta tu repositorio `music-bot`

### Paso 2: Configurar variables de entorno

En el dashboard de Railway:

1. Ve a tu proyecto
2. Click en "Variables"
3. Añade `DISCORD_TOKEN` con tu token de bot de Discord

### Paso 3: Desplegar

Railway detectará automáticamente el `Dockerfile` y desplegará tu bot.

## 📖 Comandos

### Comandos con prefijo (`!`)

- `!play <canción>` - Reproduce una canción o playlist
- `!skip` - Salta la canción actual
- `!pause` - Pausa la música
- `!resume` - Reanuda la música
- `!stop` - Para la música y vacía la cola
- `!queue` - Muestra la cola de canciones
- `!nowplaying` - Canción actual
- `!volume <0-100>` - Ajusta volumen
- `!loop [song|queue|off]` - Activa bucle
- `!remove <número>` - Elimina canción de cola
- `!shuffle` - Mezcla la cola
- `!leave` - Desconecta el bot
- `!move <origen> <destino>` - Mueve canción en cola

### Comandos slash (`/`)

- `/play` - Reproduce canción o playlist
- `/skip` - Salta canción
- `/queue` - Muestra cola
- `/stop` - Para música
- `/leave` - Desconecta bot

## 🔧 Troubleshooting

**El bot no se conecta a Discord:**
- Verifica que `DISCORD_TOKEN` está configurado correctamente en Railway
- Asegúrate de que el bot tiene permisos en tu servidor Discord

**Error de FFmpeg:**
- Railway instala FFmpeg automáticamente mediante el Dockerfile
- Si tienes problemas, el bot intentará instalarlo automáticamente

**No reproduce música:**
- Verifica que el bot está en un canal de voz contigo
- Intenta de nuevo con `/play`

## 📝 Licencia

Este proyecto es de código abierto.

## 🤝 Contribuciones

¡Las contribuciones son bienvenidas! Siéntete libre de hacer fork y abrir un PR.
