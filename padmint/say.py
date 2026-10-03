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
    "windows_here": {"en": "This Windows PC (experimental)", "es": "Este PC con Windows (experimental)",
                     "pt": "Este PC com Windows (experimental)"},
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
    "platform_windows": {"en": "Windows", "es": "Windows", "pt": "Windows"},
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
    "no_build": {"en": "no build needed", "es": "no hace falta crearlo", "pt": "não precisa criar"},
    "download_intro": {
        "en": "\n{name} needs no build: its app contains no game files, and you add your own. To get it:",
        "es": "\nNo hace falta crear {name}: su app no trae archivos del juego y tú añades los tuyos. Para conseguirlo:",
        "pt": "\nNão é preciso criar {name}: o app não traz arquivos do jogo e você adiciona os seus. Para obtê-lo:",
    },
    "build_stopped": {
        "en": ("\nThe build stopped; the lines above say why. For help, post them with your computer "
               "type (Windows, Mac or Linux) at {url}"),
        "es": ("\nLa compilación se detuvo; las líneas de arriba dicen por qué. Para pedir ayuda, "
               "publícalas junto con tu tipo de computadora (Windows, Mac o Linux) en {url}"),
        "pt": ("\nA compilação parou; as linhas acima dizem o motivo. Para pedir ajuda, publique-as "
               "com o tipo do seu computador (Windows, Mac ou Linux) em {url}"),
    },
    # The PadMint window (padmint ui).
    "w_open": {
        "en": ("PadMint {version} is open in your web browser.\nKeep this window open while PadMint works; "
               "close it when you are done.\nIf no browser opened, go to: {url}"),
        "es": ("PadMint {version} está abierto en tu navegador.\nDeja esta ventana abierta mientras PadMint "
               "trabaja; ciérrala cuando termines.\nSi no se abrió el navegador, ve a: {url}"),
        "pt": ("O PadMint {version} está aberto no seu navegador.\nDeixe esta janela aberta enquanto o "
               "PadMint trabalha; feche-a quando terminar.\nSe o navegador não abriu, acesse: {url}"),
    },
    "w_intro": {
        "en": "Make your own copy of a game from your own game file. Everything stays on this device.",
        "es": "Crea tu propia copia de un juego a partir de tu propio archivo del juego. Todo se queda en este dispositivo.",
        "pt": "Crie sua própria cópia de um jogo a partir do seu próprio arquivo do jogo. Tudo fica neste dispositivo.",
    },
    "w_language": {"en": "Language", "es": "Idioma", "pt": "Idioma"},
    "w_game": {"en": "Game", "es": "Juego", "pt": "Jogo"},
    "w_pick_game": {"en": "Choose your game", "es": "Elige tu juego", "pt": "Escolha o seu jogo"},
    "w_no_build": {"en": "No build needed: download the app, add your own files",
                   "es": "No hace falta crearlos: descarga la app y añade tus archivos",
                   "pt": "Não precisam ser criados: baixe o app e adicione seus arquivos"},
    "w_file": {"en": "Your own game file", "es": "Tu propio archivo del juego", "pt": "O seu próprio arquivo do jogo"},
    "w_file_in_app": {
        "en": "{name} asks for your game file inside the app, after you install it. Nothing to choose here.",
        "es": "{name} te pide tu archivo del juego dentro de la app, después de instalarla. Aquí no hay que elegir nada.",
        "pt": "{name} pede o seu arquivo do jogo dentro do app, depois de instalá-lo. Nada para escolher aqui.",
    },
    "w_choose": {"en": "Choose file…", "es": "Elegir archivo…", "pt": "Escolher arquivo…"},
    "w_found": {"en": "Game files in {folder}:", "es": "Archivos de juegos en {folder}:",
                "pt": "Arquivos de jogos em {folder}:"},
    "w_type": {"en": "Or type or paste the file's full path:", "es": "O escribe o pega la ruta completa del archivo:",
               "pt": "Ou digite ou cole o caminho completo do arquivo:"},
    "w_use": {"en": "Use", "es": "Usar", "pt": "Usar"},
    "w_file_ok": {"en": "Ready: {file}", "es": "Listo: {file}", "pt": "Pronto: {file}"},
    "w_wrong_game": {"en": "This file is not a {name} game file.", "es": "Este archivo no es del juego {name}.",
                     "pt": "Este arquivo não é do jogo {name}."},
    "w_not_game_file": {
        "en": "{file} is not a game file. {name} needs your own game file ({formats}), not the app.",
        "es": "{file} no es un archivo del juego. {name} necesita tu propio archivo del juego ({formats}), no la app.",
        "pt": "{file} não é um arquivo do jogo. {name} precisa do seu próprio arquivo do jogo ({formats}), não do app.",
    },
    "w_device": {"en": "Make it for", "es": "Crear para", "pt": "Criar para"},
    "w_make": {"en": "Make my copy", "es": "Crear mi copia", "pt": "Criar minha cópia"},
    "w_time": {
        "en": ("The first build usually takes 30 minutes to a few hours. Keep this page and PadMint open "
               "(its window, or Termux on a phone); you can do other things meanwhile."),
        "es": ("La primera vez suele tardar de 30 minutos a unas horas. Deja abiertos esta página y PadMint "
               "(su ventana, o Termux en un teléfono); mientras tanto puedes hacer otras cosas."),
        "pt": ("A primeira vez costuma levar de 30 minutos a algumas horas. Deixe esta página e o PadMint "
               "abertos (a janela dele, ou o Termux no celular); enquanto isso, você pode fazer outras coisas."),
    },
    "w_step_tools": {"en": "Step 1 of 3: getting the free build tools (first time only)",
                     "es": "Paso 1 de 3: descargando las herramientas gratuitas (solo la primera vez)",
                     "pt": "Etapa 1 de 3: baixando as ferramentas gratuitas (só na primeira vez)"},
    "w_step_build": {"en": "Step 2 of 3: building your copy", "es": "Paso 2 de 3: creando tu copia",
                     "pt": "Etapa 2 de 3: criando sua cópia"},
    "w_step_done": {"en": "Step 3 of 3: done!", "es": "Paso 3 de 3: ¡listo!", "pt": "Etapa 3 de 3: pronto!"},
    "w_starting": {"en": "Starting…", "es": "Empezando…", "pt": "Começando…"},
    "w_elapsed": {"en": "Time so far", "es": "Tiempo transcurrido", "pt": "Tempo até agora"},
    "w_now": {"en": "Now", "es": "Ahora", "pt": "Agora"},
    "w_cancel": {"en": "Cancel", "es": "Cancelar", "pt": "Cancelar"},
    "w_cancelled": {
        "en": "Cancelled. Finished work is kept, so the next try is faster.",
        "es": "Cancelado. Lo ya hecho se conserva, así que el siguiente intento será más rápido.",
        "pt": "Cancelado. O que já foi feito fica guardado, então a próxima tentativa é mais rápida.",
    },
    "w_details": {"en": "Details", "es": "Detalles", "pt": "Detalhes"},
    "w_copy": {"en": "Copy details", "es": "Copiar detalles", "pt": "Copiar detalhes"},
    "w_copied": {"en": "Copied", "es": "Copiado", "pt": "Copiado"},
    "w_failed": {
        "en": ("The build stopped. The details below say why. For help, copy them and post them with "
               "your computer type (Windows, Mac or Linux) at"),
        "es": ("La compilación se detuvo. Los detalles de abajo dicen por qué. Para pedir ayuda, cópialos "
               "y publícalos junto con tu tipo de computadora (Windows, Mac o Linux) en"),
        "pt": ("A compilação parou. Os detalhes abaixo dizem o motivo. Para pedir ajuda, copie-os e "
               "publique-os com o tipo do seu computador (Windows, Mac ou Linux) em"),
    },
    "w_show": {"en": "Show in folder", "es": "Mostrar en la carpeta", "pt": "Mostrar na pasta"},
    "w_next": {"en": "What to do next:", "es": "Qué hacer ahora:", "pt": "O que fazer agora:"},
    "w_guide": {"en": "Full guide", "es": "Guía completa (en inglés)", "pt": "Guia completo (em inglês)"},
    "w_again": {"en": "Make another copy", "es": "Crear otra copia", "pt": "Criar outra cópia"},
    "w_none": {"en": "No game can be made on this computer yet.",
               "es": "Todavía no se puede crear ningún juego en esta computadora.",
               "pt": "Ainda não é possível criar nenhum jogo neste computador."},

    "w_trust_local": {"en": "Runs only on this computer", "es": "Funciona solo en esta computadora",
                      "pt": "Funciona só neste computador"},
    "w_trust_upload": {"en": "Nothing is uploaded", "es": "No se sube nada", "pt": "Nada é enviado"},
    "w_trust_open": {"en": "Free, open-source tools", "es": "Herramientas libres y gratuitas",
                     "pt": "Ferramentas livres e gratuitas"},
    "w_step1": {"en": "1. Choose a game", "es": "1. Elige un juego", "pt": "1. Escolha um jogo"},
    "w_step2": {"en": "2. Your own game file", "es": "2. Tu propio archivo del juego",
                "pt": "2. O seu próprio arquivo do jogo"},
    "w_step3": {"en": "3. Make it for", "es": "3. Crear para", "pt": "3. Criar para"},
    "w_search": {"en": "Search games", "es": "Buscar juegos", "pt": "Buscar jogos"},
    "w_builds": {"en": "Made on this computer from your game file", "es": "Se crean en esta computadora con tu archivo del juego",
                 "pt": "Criados neste computador com o seu arquivo do jogo"},
    "w_file_hint": {"en": "Your own copy of {game}.", "es": "Tu propia copia de {game}.", "pt": "A sua própria cópia de {game}."},
    "w_file_formats": {"en": "Accepted: {formats}", "es": "Formatos aceptados: {formats}", "pt": "Formatos aceitos: {formats}"},
    "w_file_ids": {"en": "Disc ID {ids}", "es": "ID del disco {ids}", "pt": "ID do disco {ids}"},
    "w_stage": {"en": "Current step: {stage}", "es": "Paso actual: {stage}", "pt": "Etapa atual: {stage}"},
    "w_what_you_got": {"en": "What you got", "es": "Lo que obtuviste", "pt": "O que você recebeu"},
    "w_change": {"en": "Change game", "es": "Cambiar de juego", "pt": "Trocar de jogo"},
    "w_type_toggle": {"en": "Type a path instead", "es": "Escribir una ruta", "pt": "Digitar um caminho"},
    "w_plan_title": {"en": "What PadMint will do on this computer", "es": "Qué hará PadMint en esta computadora",
                     "pt": "O que o PadMint vai fazer neste computador"},
    "w_plan_source": {"en": "Download {name}'s source code (latest release) from {repo}",
                      "es": "Descargar el código fuente de {name} (última versión) desde {repo}",
                      "pt": "Baixar o código-fonte de {name} (última versão) de {repo}"},
    "w_plan_tools": {"en": "Download the free build tools it needs, once, into {folder}:",
                     "es": "Descargar una sola vez las herramientas gratuitas que necesita, en {folder}:",
                     "pt": "Baixar uma única vez as ferramentas gratuitas necessárias, em {folder}:"},
    "w_tool_here": {"en": "already on this computer", "es": "ya está en esta computadora", "pt": "já está neste computador"},
    "w_plan_app": {"en": "Download {name}'s published app, which has no game code in it",
                   "es": "Descargar la app publicada de {name}, que no contiene código del juego",
                   "pt": "Baixar o app publicado de {name}, que não contém código do jogo"},
    "w_plan_build": {"en": "Build your copy here from your game file: the first time takes 30 minutes to a few hours, later builds reuse finished work",
                     "es": "Crear tu copia aquí con tu archivo del juego: la primera vez tarda de 30 minutos a unas horas; después se reutiliza lo hecho",
                     "pt": "Criar sua cópia aqui com o seu arquivo do jogo: a primeira vez leva de 30 minutos a algumas horas; depois o que foi feito é reaproveitado"},
    "w_plan_save": {"en": "Save your copy in {folder}", "es": "Guardar tu copia en {folder}", "pt": "Salvar sua cópia em {folder}"},
    "w_plan_space": {"en": "Free space needed: about {gb} GB", "es": "Espacio libre necesario: unos {gb} GB",
                     "pt": "Espaço livre necessário: cerca de {gb} GB"},
    "w_plan_needs": {"en": "Install this yourself first:", "es": "Instala esto antes por tu cuenta:",
                     "pt": "Instale isto antes por conta própria:"},
    "w_needs_ok": {"en": "found", "es": "encontrado", "pt": "encontrado"},
    "w_needs_missing": {"en": "not found", "es": "no encontrado", "pt": "não encontrado"},
    "w_output_android": {"en": "You get a game pack (a .so file) and a game data folder. Both go into the {name} app on your Android phone or tablet.",
                         "es": "Recibes un paquete del juego (un archivo .so) y una carpeta de datos del juego. Ambos se añaden en la app {name} de tu teléfono o tableta Android.",
                         "pt": "Você recebe um pacote do jogo (um arquivo .so) e uma pasta de dados do jogo. Os dois são adicionados no app {name} do seu celular ou tablet Android."},
    "w_output_ios": {"en": "You get an .ipa app file. You install it on your iPhone or iPad with a sideloading tool such as AltStore or Sideloadly and your own Apple ID.",
                     "es": "Recibes un archivo de app .ipa. Lo instalas en tu iPhone o iPad con una herramienta como AltStore o Sideloadly y tu propio Apple ID.",
                     "pt": "Você recebe um arquivo de app .ipa. Você o instala no seu iPhone ou iPad com uma ferramenta como AltStore ou Sideloadly e o seu próprio Apple ID."},
    "w_output_macos": {"en": "You get a Mac app to open on this Mac.", "es": "Recibes una app para abrir en este Mac.",
                       "pt": "Você recebe um app para abrir neste Mac."},
    "w_output_windows": {"en": "You get a folder with {name}.exe to play on this PC.",
                         "es": "Recibes una carpeta con {name}.exe para jugar en este PC.",
                         "pt": "Você recebe uma pasta com {name}.exe para jogar neste PC."},
    "w_making": {"en": "Making {name} for {device}", "es": "Creando {name} para {device}", "pt": "Criando {name} para {device}"},
    "w_ph_release": {"en": "Find the latest {name} release", "es": "Buscar la última versión de {name}",
                     "pt": "Encontrar a última versão de {name}"},
    "w_ph_source": {"en": "Download {name}'s source code", "es": "Descargar el código fuente de {name}",
                    "pt": "Baixar o código-fonte de {name}"},
    "w_ph_tools": {"en": "Get the free build tools", "es": "Obtener las herramientas gratuitas",
                   "pt": "Obter as ferramentas gratuitas"},
    "w_ph_app": {"en": "Download {name}'s app (no game code inside)", "es": "Descargar la app de {name} (sin código del juego)",
                 "pt": "Baixar o app de {name} (sem código do jogo)"},
    "w_ph_build": {"en": "Build your copy on this computer", "es": "Crear tu copia en esta computadora",
                   "pt": "Criar sua cópia neste computador"},
    "w_ph_save": {"en": "Save your copy", "es": "Guardar tu copia", "pt": "Salvar sua cópia"},
    "w_from": {"en": "from {host}", "es": "desde {host}", "pt": "de {host}"},
    "w_version_from": {"en": "{version}, from {repo}", "es": "{version}, desde {repo}", "pt": "{version}, de {repo}"},
    "w_unpacking": {"en": "unpacking", "es": "descomprimiendo", "pt": "descompactando"},
    "w_log": {"en": "Technical log", "es": "Registro técnico", "pt": "Registro técnico"},
    "w_log_empty": {"en": "Nothing written yet.", "es": "Todavía no hay nada escrito.", "pt": "Nada escrito ainda."},
    "w_copy_log": {"en": "Copy log for a bug report", "es": "Copiar registro para un informe", "pt": "Copiar registro para um relato"},
    "w_done_title": {"en": "Your copy is ready", "es": "Tu copia está lista", "pt": "Sua cópia está pronta"},
    "w_failed_title": {"en": "The build stopped", "es": "La compilación se detuvo", "pt": "A compilação parou"},
    "w_cancel_note": {"en": "Cancel keeps finished work, so the next try is faster.",
                      "es": "Cancelar conserva lo ya hecho, así que el siguiente intento será más rápido.",
                      "pt": "Cancelar guarda o que já foi feito, então a próxima tentativa é mais rápida."},
    "w_source": {"en": "PadMint source code", "es": "Código fuente de PadMint", "pt": "Código-fonte do PadMint"},
    "w_report": {"en": "Report a problem", "es": "Informar un problema", "pt": "Relatar um problema"},
    "w_local_note": {"en": "This page is served by PadMint on this computer (127.0.0.1).",
                     "es": "Esta página la sirve PadMint en esta computadora (127.0.0.1).",
                     "pt": "Esta página é servida pelo PadMint neste computador (127.0.0.1)."},
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
    chosen = language()
    if chosen != "en" and not stream_supports():
        chosen = "en"
    return phrase(key, chosen, **fields)


def phrase(key, lang, **fields):
    """The message for key in the given language (the PadMint window chooses its own)."""
    texts = MESSAGES[key]
    return texts.get(lang, texts["en"]).format(**fields)


def localized(value, field, lang=None):
    """A catalog value's translation (value["translations"][lang][field]) or the English original."""
    chosen = lang or (language() if stream_supports() else "en")
    return ((value.get("translations") or {}).get(chosen) or {}).get(field, value.get(field))


def stream_supports(stream=None):
    """True when stream can print this language's characters (always, on modern terminals)."""
    encoding = getattr(stream or sys.stdout, "encoding", None) or "utf-8"
    try:
        "áéíóúãçñ¿¡…".encode(encoding)
        return True
    except (LookupError, UnicodeEncodeError):
        return False
