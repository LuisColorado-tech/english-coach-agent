# English Coach Agent (ECA-1)

Agente de IA conversacional para práctica de inglés en tiempo real. Corre 24/7 en Windows como compañía persistente. Habla, escucha, corrige gramática en tiempo real, recuerda el perfil del usuario entre sesiones, y puede iniciar conversaciones espontáneas.

## Arquitectura

Construido sobre **Pipecat** como orquestador de pipeline:

```
Micrófono → VAD (Silero) → STT (Faster-Whisper) → LLM (DeepSeek) → TTS (edge-tts) → Parlantes
                                        ↕
                              SQLite + JSON (memoria)
                                        ↕
                              UI (customtkinter)
```

## Requisitos

- Python 3.11+
- Windows 10/11
- Micrófono y parlantes
- API key de DeepSeek (gratis, obtener en [platform.deepseek.com](https://platform.deepseek.com))
- Conexión a internet (para DeepSeek API y edge-tts)

## Instalación

```bash
# Clonar o copiar el proyecto
cd english-coach-agent

# Ejecutar setup (instala dependencias, descarga modelos, wizard de configuración)
python setup.py
```

## Uso

```bash
# Iniciar el agente
python run.py

# O en Windows, doble clic en run.bat
```

### Comandos del System Tray

- **Abrir panel** — Muestra la ventana de transcripción
- **Pausar / Reanudar** — Pausa o reanuda la escucha
- **Ver estadísticas** — Muestra métricas de progreso
- **Salir** — Cierra el agente

## Configuración

Editar `.env`:

| Variable | Descripción | Default |
|---|---|---|
| `DEEPSEEK_API_KEY` | API key de DeepSeek (requerida) | - |
| `ECA_LOG_LEVEL` | Nivel de logging | `INFO` |
| `ECA_WHISPER_MODEL` | Modelo de Whisper | `base.en` |
| `ECA_TTS_VOICE` | Voz de edge-tts | `en-US-AriaNeural` |
| `ECA_SPONTANEOUS_ENABLED` | Modo espontáneo | `true` |

## Estructura del proyecto

```
english-coach-agent/
├── config/          # Configuración global
├── core/            # Pipeline, agente, scheduler
├── stt/             # Speech-to-text (faster-whisper)
├── llm/             # Cliente DeepSeek y parser
├── tts/             # Text-to-speech (edge-tts)
├── memory/          # Perfil y sesiones (SQLite + JSON)
├── ui/              # Interfaz gráfica (customtkinter)
├── data/            # Datos de usuario (no commitear)
├── assets/          # Iconos y sonidos
├── tests/           # Tests con pytest
├── scripts/         # Utilidades
├── run.py           # Entry point
├── setup.py         # Instalador
└── run.bat          # Launcher para Windows
```

## Stack tecnológico

| Componente | Tecnología |
|---|---|
| Pipeline | Pipecat AI |
| STT | Faster-Whisper (local) |
| LLM | DeepSeek Chat |
| TTS | Microsoft Edge TTS |
| VAD | Silero VAD |
| UI | customtkinter |
| Memoria | SQLite + JSON |
| Logging | Loguru |

## Licencia

MIT
