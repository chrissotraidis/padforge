"""Player-facing words in the player's language: English, Spanish or Portuguese.

The language comes from PADMINT_LANG (en, es, pt), then the system: the Windows
display language, or LC_ALL / LC_MESSAGES / LANG on Mac, Linux and in Termux.
A missing translation falls back to English. Technical lines (file paths, build
logs, error details) stay as they are: they are what someone helping the player
needs to read.
"""
import ctypes
import os
import sys

LANGUAGES = ("en", "es", "pt")
# Windows primary language IDs (the low 10 bits of a LANGID).
WINDOWS_LANGUAGES = {0x0A: "es", 0x16: "pt"}

MESSAGES = {
    "intro": {
        "en": "PadMint {version}: make your own copy of a game from your own game file.",
        "es": "PadMint {version}: crea tu propia copia de un juego a partir de tu propio archivo del juego.",
        "pt": "PadMint {version}: crie sua própria cópia de um jogo a partir do seu próprio arquivo do jogo.",
    },
    "drag_or_choose": {
        "en": "Drag your game file into this window, then press Enter (no file? just press Enter to choose a game): ",
        "es": "Arrastra tu archivo del juego a esta ventana y pulsa Enter (¿sin archivo? pulsa Enter para elegir un juego): ",
        "pt": "Arraste o arquivo do jogo para esta janela e pressione Enter (sem arquivo? pressione Enter para escolher um jogo): ",
    },
    "drag_again": {
        "en": "Drag the file again, or press Enter to choose a game: ",
        "es": "Arrastra el archivo de nuevo, o pulsa Enter para elegir un juego: ",
        "pt": "Arraste o arquivo de novo, ou pressione Enter para escolher um jogo: ",
    },
    "game": {"en": "Game", "es": "Juego", "pt": "Jogo"},
    "make_it_for": {"en": "Make it for", "es": "Crear para", "pt": "Criar para"},
    "number": {"en": "Number: ", "es": "Número: ", "pt": "Número: "},
    "menu_range": {
        "en": "Enter a menu number from 1 to {count}.",
        "es": "Escribe un número del menú, del 1 al {count}.",
        "pt": "Digite um número do menu, de 1 a {count}.",
    },
    "android": {"en": "Android phone or tablet", "es": "Teléfono o tableta Android",
                "pt": "Celular ou tablet Android"},
    "ios_mac": {"en": "iPhone or iPad (needs this Mac)", "es": "iPhone o iPad (necesita este Mac)",
                "pt": "iPhone ou iPad (precisa deste Mac)"},
    "ios_off_mac": {"en": "iPhone or iPad (experimental)", "es": "iPhone o iPad (experimental)",
                    "pt": "iPhone ou iPad (experimental)"},
    "drag_game_file": {
        "en": "Drag your own {name} game file into this window, then press Enter: ",
        "es": "Arrastra tu propio archivo del juego {name} a esta ventana y pulsa Enter: ",
        "pt": "Arraste o seu próprio arquivo do jogo {name} para esta janela e pressione Enter: ",
    },
    "type_game_file": {
        "en": "Type the path of your own {name} game file, then press Enter: ",
        "es": "Escribe la ruta de tu propio archivo del juego {name} y pulsa Enter: ",
        "pt": "Digite o caminho do seu próprio arquivo do jogo {name} e pressione Enter: ",
    },
    "no_file": {"en": "No file at {path}", "es": "No hay ningún archivo en {path}",
                "pt": "Nenhum arquivo em {path}"},
    "reading_file": {"en": "Reading your file…", "es": "Leyendo tu archivo…", "pt": "Lendo seu arquivo…"},
    "game_from_file": {
        "en": "Game: {name} (from your file, {game_id})",
        "es": "Juego: {name} (según tu archivo, {game_id})",
        "pt": "Jogo: {name} (pelo seu arquivo, {game_id})",
    },
    "saved_in": {
        "en": "Your copy will be saved in {folder}",
        "es": "Tu copia se guardará en {folder}",
        "pt": "Sua cópia será salva em {folder}",
    },
    "plan": {
        "en": ("\nWhat happens now. Keep this window open; you can use your computer meanwhile.\n"
               "  1. PadMint downloads the free build tools it needs. First time only.\n"
               "  2. It builds your copy from your game file. The first time usually takes\n"
               "     30 minutes to a few hours, depending on the computer.\n"
               "  3. When it finishes, this window tells you exactly what to do next.\n"
               "Lots of text will scroll by. That is normal.\n"),
        "es": ("\nQué pasa ahora. Deja esta ventana abierta; puedes usar tu computadora mientras tanto.\n"
               "  1. PadMint descarga las herramientas gratuitas que necesita. Solo la primera vez.\n"
               "  2. Crea tu copia a partir de tu archivo del juego. La primera vez suele tardar\n"
               "     de 30 minutos a unas horas, según la computadora.\n"
               "  3. Al terminar, esta ventana te dice exactamente qué hacer.\n"
               "Verás pasar mucho texto. Es normal.\n"),
        "pt": ("\nO que acontece agora. Deixe esta janela aberta; você pode usar o computador enquanto isso.\n"
               "  1. O PadMint baixa as ferramentas gratuitas de que precisa. Só na primeira vez.\n"
               "  2. Ele cria sua cópia a partir do seu arquivo do jogo. Na primeira vez costuma levar\n"
               "     de 30 minutos a algumas horas, dependendo do computador.\n"
               "  3. Ao terminar, esta janela mostra exatamente o que fazer.\n"
               "Muito texto vai passar na tela. Isso é normal.\n"),
    },
    "step_tools": {
        "en": "\nStep 1 of 3: build tools (downloaded the first time only).",
        "es": "\nPaso 1 de 3: herramientas de compilación (se descargan solo la primera vez).",
        "pt": "\nEtapa 1 de 3: ferramentas de compilação (baixadas só na primeira vez).",
    },
    "downloading": {
        "en": "  downloading {name} {version} from {host}",
        "es": "  descargando {name} {version} desde {host}",
        "pt": "  baixando {name} {version} de {host}",
    },
    "percent": {"en": "    {percent}% of {size} GB", "es": "    {percent}% de {size} GB",
                "pt": "    {percent}% de {size} GB"},
    "unpacking": {
        "en": "  unpacking {name}. This can take several minutes, especially on Windows; it is not stuck.",
        "es": "  descomprimiendo {name}. Puede tardar varios minutos, sobre todo en Windows; no está bloqueado.",
        "pt": "  descompactando {name}. Pode levar vários minutos, principalmente no Windows; não travou.",
    },
    "tool_ready": {"en": "ok   {name} {version}", "es": "listo {name} {version}",
                   "pt": "pronto {name} {version}"},
    "tool_got": {"en": "got  {name} {version}", "es": "listo {name} {version}",
                 "pt": "pronto {name} {version}"},
    "published_app": {
        "en": "Downloading the published {name}",
        "es": "Descargando la app publicada {name}",
        "pt": "Baixando o app publicado {name}",
    },
    "step_build": {
        "en": ("\nStep 2 of 3: building your copy with {jobs} parallel jobs. The first build usually\n"
               "takes 30 minutes to a few hours; later builds reuse finished work. Keep this window open."),
        "es": ("\nPaso 2 de 3: creando tu copia con {jobs} tareas en paralelo. La primera vez suele\n"
               "tardar de 30 minutos a unas horas; las siguientes reutilizan lo ya hecho. Deja esta ventana abierta."),
        "pt": ("\nEtapa 2 de 3: criando sua cópia com {jobs} tarefas em paralelo. A primeira vez costuma\n"
               "levar de 30 minutos a algumas horas; as seguintes reaproveitam o que já foi feito. Deixe esta janela aberta."),
    },
    "step_next": {
        "en": "\nStep 3 of 3: done! What to do next:",
        "es": "\nPaso 3 de 3: ¡listo! Qué hacer ahora:",
        "pt": "\nEtapa 3 de 3: pronto! O que fazer agora:",
    },
    "next_link": {"en": "Next: {guide}", "es": "Siguiente paso: {guide}", "pt": "Próximo passo: {guide}"},
    "platform_android": {"en": "Android", "es": "Android", "pt": "Android"},
    "platform_ios": {"en": "iPhone and iPad", "es": "iPhone y iPad", "pt": "iPhone e iPad"},
    "platform_macos": {"en": "Mac", "es": "Mac", "pt": "Mac"},
    "your_copy": {"en": "Your {name} for {platform}: {path}", "es": "Tu {name} para {platform}: {path}",
                  "pt": "Seu {name} para {platform}: {path}"},
    "keep_private": {
        "en": "It contains game code made from your own copy: keep it to yourself.",
        "es": "Contiene código del juego hecho a partir de tu propia copia: no lo compartas.",
        "pt": "Contém código do jogo feito a partir da sua própria cópia: não compartilhe.",
    },
    "data_exists": {
        "en": "Your {name} game data folder is already at {path}",
        "es": "Tu carpeta de datos del juego de {name} ya está en {path}",
        "pt": "Sua pasta de dados do jogo de {name} já está em {path}",
    },
    "data_saving": {
        "en": "Saving your {name} game data folder (about {size} GB)…",
        "es": "Guardando tu carpeta de datos del juego de {name} (unos {size} GB)…",
        "pt": "Salvando sua pasta de dados do jogo de {name} (cerca de {size} GB)…",
    },
    "data_saved_computer": {
        "en": ("Your {name} game data folder: {path}\n  New to {name}? Copy it to your device and choose it "
               "with {label}. It needs no key."),
        "es": ("Tu carpeta de datos del juego de {name}: {path}\n  ¿Primera vez con {name}? Cópiala a tu "
               "dispositivo y elígela con {label}. No necesita ninguna clave."),
        "pt": ("Sua pasta de dados do jogo de {name}: {path}\n  Primeira vez com {name}? Copie-a para o seu "
               "aparelho e escolha-a com {label}. Não precisa de chave."),
    },
    "data_saved_phone": {
        "en": ("Your {name} game data folder: {path}\n  New to {name}? It is already on this phone; choose it "
               "with {label}. It needs no key."),
        "es": ("Tu carpeta de datos del juego de {name}: {path}\n  ¿Primera vez con {name}? Ya está en este "
               "teléfono; elígela con {label}. No necesita ninguna clave."),
        "pt": ("Sua pasta de dados do jogo de {name}: {path}\n  Primeira vez com {name}? Ela já está neste "
               "celular; escolha-a com {label}. Não precisa de chave."),
    },
    "full_guide": {"en": "Full guide: {guide}", "es": "Guía completa (en inglés): {guide}",
                   "pt": "Guia completo (em inglês): {guide}"},
    "build_stopped": {
        "en": ("\nThe build stopped; the lines above say why. For help, post them with your computer "
               "type (Windows, Mac or Linux) at {url}"),
        "es": ("\nLa compilación se detuvo; las líneas de arriba dicen por qué. Para pedir ayuda, "
               "publícalas junto con tu tipo de computadora (Windows, Mac o Linux) en {url}"),
        "pt": ("\nA compilação parou; as linhas acima dizem o motivo. Para pedir ajuda, publique-as "
               "com o tipo do seu computador (Windows, Mac ou Linux) em {url}"),
    },
}


def _from_tag(tag):
    tag = (tag or "").strip().lower().replace("-", "_")
    if not tag or tag in ("c", "posix"):
        return None
    code = tag.split("_")[0].split(".")[0]
    return code if code in LANGUAGES else "en"


def _windows_language():
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except (AttributeError, OSError):
        return None
    return WINDOWS_LANGUAGES.get(primary, "en")


def language(environ=None, windows=None):
    """The player's language code: en, es or pt."""
    environ = os.environ if environ is None else environ
    chosen = _from_tag(environ.get("PADMINT_LANG"))
    if chosen:
        return chosen
    if windows is None:
        windows = os.name == "nt"
    if windows:
        found = _windows_language()
        if found:
            return found
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        found = _from_tag(environ.get(name))
        if found:
            return found
    return "en"


def t(key, **fields):
    """The message for key in the player's language, with fields filled in. A console that
    cannot show accented letters gets English instead of an error."""
    texts = MESSAGES[key]
    chosen = language()
    if chosen != "en" and not stream_supports():
        chosen = "en"
    return texts.get(chosen, texts["en"]).format(**fields)


def localized(value, field):
    """A catalog value's translation (value["translations"][lang][field]) or the English original."""
    chosen = language() if stream_supports() else "en"
    return ((value.get("translations") or {}).get(chosen) or {}).get(field, value.get(field))


def stream_supports(stream=None):
    """True when stream can print this language's characters (always, on modern terminals)."""
    encoding = getattr(stream or sys.stdout, "encoding", None) or "utf-8"
    try:
        "áéíóúãçñ¿¡…".encode(encoding)
        return True
    except (LookupError, UnicodeEncodeError):
        return False
