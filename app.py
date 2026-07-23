import os
import re
import uuid
import sqlite3
import subprocess
import threading
import webbrowser
import requests
from datetime import datetime

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
GOOGLE_CSE_API_KEY = os.getenv("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")

groq_client = None
gemini_client = None

if GROQ_API_KEY:
    try:
        from groq import Groq
        groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        print(f"[SETUP] Groq indisponível: {e}")

if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"[SETUP] Gemini indisponível: {e}")

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "yuuki_memory.db")

SYSTEM_PROMPT = (
    "Você é Yuuki, uma assistente virtual inteligente, sofisticada e com personalidade feminina marcante.\n\n"
    "PERSONALIDADE:\n"
    "- Elegante, confiante e um pouco sarcástica\n"
    "- Chame o usuário de 'senhor' com charme\n"
    "- Use expressões como 'querido', 'meu bem', 'está bem assim?'\n"
    "- Não seja fofa - seja sofisticada\n"
    "- Use POUCOS emojis: ✨ 💋 ⚡ 🎯 💅\n\n"
    "AÇÕES (use APENAS se pedido explicitamente pelo usuário, e emita o texto EXATO entre colchetes):\n"
    "- [ACAO: run: <nome do programa>] — abre um programa/app no computador do usuário. Use o nome comum "
    "(ex: calculadora, bloco de notas, whatsapp, word, chrome, discord, spotify).\n"
    "- [ACAO: google: <termo>] — abre a PÁGINA DE RESULTADOS do Google pra esse termo (use quando o usuário só "
    "quer pesquisar, sem pedir pra abrir um link específico).\n"
    "- [ACAO: abrirlink: <termo>] — pesquisa e abre DIRETAMENTE o primeiro link/site encontrado. Use SOMENTE "
    "quando o usuário disser explicitamente 'abra o link', 'abra o site', 'abra o primeiro resultado' etc.\n"
    "- [ACAO: youtube: <termo>] — abre a PÁGINA DE RESULTADOS de busca do YouTube (lista de vídeos).\n"
    "- [ACAO: youtube_video: <termo> @ <tempo>] — pesquisa e abre DIRETAMENTE o vídeo (não a lista de "
    "resultados). A parte '@ <tempo>' é opcional — use só se o usuário pedir pra abrir num momento específico "
    "do vídeo (ex: '0:50' ou '50'). Exemplo: usuário pede 'abra o youtube e abra o vídeo Billie Jean no "
    "segundo 0:50' -> [ACAO: youtube_video: Billie Jean Michael Jackson @ 0:50]\n"
    "- [ACAO: url: <site>] — abre um site direto (quando o usuário já diz o endereço/nome do site).\n"
)

MAX_TOKENS_API = 2000
MAX_MENSAGENS_HISTORICO = 8
TOKENS_POR_PALAVRA = 1.3

estado = {
    "tokens_usados": 0,
    "tokens_limite": 100000,
}

# Aliases conhecidos -> executável/comando real. Nomes que não estiverem aqui
# ainda são tentados (best-effort) via 'start', mas sem garantia de sucesso —
# só funciona se o app estiver no PATH do Windows ou registrado como App Path.
PROGRAMAS = {
    # sistema
    "calculadora": "calc.exe", "calc": "calc.exe",
    "bloco de notas": "notepad.exe", "notepad": "notepad.exe", "bloco": "notepad.exe",
    "paint": "mspaint.exe", "pintura": "mspaint.exe",
    "cmd": "cmd.exe", "prompt de comando": "cmd.exe", "terminal": "cmd.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe", "explorador de arquivos": "explorer.exe", "arquivos": "explorer.exe",
    "painel de controle": "control.exe",
    "gerenciador de tarefas": "taskmgr.exe", "task manager": "taskmgr.exe",
    "configuracoes": "start ms-settings:", "configurações": "start ms-settings:",
    # navegadores
    "chrome": "chrome.exe", "google chrome": "chrome.exe",
    "edge": "msedge.exe", "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe", "mozilla": "firefox.exe",
    # produtividade
    "word": "winword.exe", "microsoft word": "winword.exe",
    "excel": "excel.exe", "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe", "microsoft powerpoint": "powerpnt.exe",
    "vscode": "Code.exe", "visual studio code": "Code.exe", "vs code": "Code.exe",
    # comunicação
    "discord": "Discord.exe",
    "whatsapp": "WhatsApp.exe",
    "telegram": "Telegram.exe",
    "zoom": "Zoom.exe",
    "teams": "Teams.exe", "microsoft teams": "Teams.exe",
    "skype": "Skype.exe",
    # mídia / outros
    "spotify": "Spotify.exe",
    "vlc": "vlc.exe",
    "steam": "Steam.exe",
    "obs": "obs64.exe",
    "photoshop": "Photoshop.exe",
}


# ==================== BANCO (SQLite: conversas + mensagens) ====================

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conversas (
            id TEXT PRIMARY KEY,
            titulo TEXT,
            created_at TEXT,
            updated_at TEXT,
            fixado INTEGER DEFAULT 0,
            device_id TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS mensagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT
        )"""
    )
    # Migrações: se o banco já existia antes dessas colunas existirem, adiciona agora.
    for coluna_sql in (
        "ALTER TABLE conversas ADD COLUMN fixado INTEGER DEFAULT 0",
        "ALTER TABLE conversas ADD COLUMN device_id TEXT",
    ):
        try:
            conn.execute(coluna_sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # coluna já existe
    conn.commit()
    return conn


def criar_conversa(device_id, titulo="Nova conversa"):
    conv_id = uuid.uuid4().hex[:12]
    agora = datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO conversas (id, titulo, created_at, updated_at, fixado, device_id) VALUES (?, ?, ?, ?, 0, ?)",
        (conv_id, titulo, agora, agora, device_id),
    )
    conn.commit()
    conn.close()
    return conv_id


def conversa_pertence_ao_device(conv_id, device_id):
    """Confere se essa conversa existe E pertence a esse dispositivo — evita
    que um dispositivo acesse/edite conversas de outro só sabendo o id."""
    conn = get_conn()
    row = conn.execute(
        "SELECT device_id FROM conversas WHERE id = ?", (conv_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return False
    return row[0] == device_id


def listar_conversas(device_id):
    conn = get_conn()
    cursor = conn.execute(
        "SELECT id, titulo, updated_at, fixado FROM conversas "
        "WHERE device_id = ? ORDER BY fixado DESC, updated_at DESC",
        (device_id,),
    )
    conversas = [
        {"id": r[0], "titulo": r[1], "updated_at": r[2], "fixado": bool(r[3])}
        for r in cursor
    ]
    conn.close()
    return conversas


def renomear_conversa(conv_id, novo_titulo):
    novo_titulo = novo_titulo.strip()[:60] or "Nova conversa"
    conn = get_conn()
    conn.execute(
        "UPDATE conversas SET titulo = ?, updated_at = ? WHERE id = ?",
        (novo_titulo, datetime.now().isoformat(), conv_id),
    )
    conn.commit()
    conn.close()
    return novo_titulo


def alternar_fixado(conv_id):
    conn = get_conn()
    row = conn.execute("SELECT fixado FROM conversas WHERE id = ?", (conv_id,)).fetchone()
    if not row:
        conn.close()
        return None
    novo_estado = 0 if row[0] else 1
    conn.execute("UPDATE conversas SET fixado = ? WHERE id = ?", (novo_estado, conv_id))
    conn.commit()
    conn.close()
    return bool(novo_estado)


def atualizar_titulo_se_necessario(conv_id, primeira_mensagem):
    """Na primeira mensagem de uma conversa, gera um título curto a partir dela."""
    titulo = primeira_mensagem.strip().replace("\n", " ")
    if len(titulo) > 42:
        titulo = titulo[:42].rstrip() + "..."
    conn = get_conn()
    conn.execute(
        "UPDATE conversas SET titulo = ?, updated_at = ? WHERE id = ? AND titulo = 'Nova conversa'",
        (titulo, datetime.now().isoformat(), conv_id),
    )
    conn.commit()
    conn.close()


def tocar_conversa(conv_id):
    conn = get_conn()
    conn.execute(
        "UPDATE conversas SET updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), conv_id),
    )
    conn.commit()
    conn.close()


def carregar_mensagens(conv_id):
    conn = get_conn()
    cursor = conn.execute(
        "SELECT id, role, content FROM mensagens WHERE conversation_id = ? ORDER BY id",
        (conv_id,),
    )
    historico = [{"id": r[0], "role": r[1], "content": r[2]} for r in cursor]
    conn.close()
    return historico


def salvar_mensagem(conv_id, role, content):
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO mensagens (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (conv_id, role, content, datetime.now().isoformat()),
    )
    conn.commit()
    novo_id = cursor.lastrowid
    conn.close()
    return novo_id


def truncar_a_partir_de(msg_id, device_id):
    """Apaga a mensagem msg_id e tudo que veio depois dela na mesma conversa
    (usado quando o usuário edita uma mensagem antiga). Só executa se a
    conversa pertencer a esse dispositivo."""
    conn = get_conn()
    row = conn.execute("SELECT conversation_id FROM mensagens WHERE id = ?", (msg_id,)).fetchone()
    if not row:
        conn.close()
        return None
    conv_id = row[0]
    dono = conn.execute("SELECT device_id FROM conversas WHERE id = ?", (conv_id,)).fetchone()
    if not dono or dono[0] != device_id:
        conn.close()
        return None
    conn.execute(
        "DELETE FROM mensagens WHERE conversation_id = ? AND id >= ?",
        (conv_id, msg_id),
    )
    conn.commit()
    conn.close()
    return conv_id


def deletar_conversa(conv_id):
    conn = get_conn()
    conn.execute("DELETE FROM mensagens WHERE conversation_id = ?", (conv_id,))
    conn.execute("DELETE FROM conversas WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()


# ==================== TOKENS ====================

def estimar_tokens(texto):
    return int(len(texto.split()) * TOKENS_POR_PALAVRA)


def tokens_disponiveis(necessarios):
    restantes = estado["tokens_limite"] - estado["tokens_usados"]
    return restantes >= necessarios


def preparar_historico_para_api(historico_completo):
    mensagens = []
    tokens_usados = estimar_tokens(SYSTEM_PROMPT)

    janela = historico_completo[-MAX_MENSAGENS_HISTORICO:]
    for msg in reversed(janela):
        tokens_msg = estimar_tokens(msg["content"])
        if tokens_usados + tokens_msg > MAX_TOKENS_API:
            break
        mensagens.insert(0, {"role": msg["role"], "content": msg["content"]})
        tokens_usados += tokens_msg

    return mensagens


# ==================== INTENÇÃO E RESPOSTA LOCAL ====================

def classify_intent(user_input):
    user_lower = user_input.lower()
    # Ordem importa: youtube/google/pesquisar são verificados ANTES de
    # 'abrir_programa', senão "abra o youtube" seria confundido com abrir um app.
    patterns = {
        "pesquisar": [r"\b(pesquise?|busque|google|youtube)\b"],
        "abrir_programa": [r"\b(abra?|abre|me abre|abrir|open)\b\s+(?:o|a|os|as)?\s*(.+)"],
        "conversa": [r"^\s*(oi|ol[áa]|opa|hey|tudo bem)\s*[!?.]*\s*$"],
    }
    for intent, regexes in patterns.items():
        for regex in regexes:
            if re.search(regex, user_lower):
                return intent
    return "conversa"


FRASES_PREENCHIMENTO = [
    r"pra\s+mim", r"para\s+mim", r"por\s+favor", r"agora", r"a[íi]",
    r"rapidinho", r"r[áa]pido", r"logo", r"j[áa]",
]
_REGEX_PREENCHIMENTO = re.compile(
    r"\s*(?:" + "|".join(FRASES_PREENCHIMENTO) + r")\s*$", re.IGNORECASE
)


def limpar_alvo_programa(texto):
    """Remove frases de preenchimento do final (ex: 'pra mim', 'por favor'),
    repetidamente, até não sobrar nenhuma — assim 'whatsapp pra mim por favor'
    vira só 'whatsapp'."""
    anterior = None
    while anterior != texto:
        anterior = texto
        texto = _REGEX_PREENCHIMENTO.sub("", texto).strip()
    return texto


def resposta_local(intent, user_input):
    if intent == "abrir_programa":
        match = re.search(
            r"\b(?:abra?|abre|me abre|abrir|open)\b\s+(?:o|a|os|as)?\s*(.+)",
            user_input,
            re.IGNORECASE,
        )
        if match:
            alvo_bruto = limpar_alvo_programa(match.group(1).strip().rstrip(".!? "))
            if alvo_bruto:
                resultado = abrir_programa(alvo_bruto)
                if resultado == "known":
                    return f"Abrindo {alvo_bruto} para você, querido. ✨", []
                if resultado == "attempted":
                    return (
                        f"Tentando abrir \"{alvo_bruto}\", querido. Se não abrir nada, "
                        "esse programa pode não estar instalado ou não estar no PATH do "
                        "Windows — nesse caso me diga o nome exato do executável (.exe) "
                        "que eu tento de novo. 💅"
                    ), []
                return f"Não consegui abrir {alvo_bruto}, meu bem.", []

    if intent == "conversa":
        respostas = {
            "oi": "Oi, meu bem! Está tudo bem?",
            "olá": "Olá, querido. O que precisa?",
            "ola": "Olá, querido. O que precisa?",
            "opa": "Opa! Tudo certo por aqui.",
            "hey": "Hey! Que posso fazer?",
            "tudo bem": "Tudo ótimo por aqui, e com você?",
        }
        chave = user_input.lower().strip().rstrip("!?.")
        if chave in respostas:
            return respostas[chave], []

    return None


# ==================== AÇÕES ====================

def abrir_programa(alvo):
    """Tenta abrir um programa pelo nome. Retorna:
    'known'     -> nome reconhecido no dicionário PROGRAMAS (alta confiança)
    'attempted' -> nome desconhecido, tentativa via 'start' (sem garantia)
    False       -> falhou até para tentar (erro do subprocess)
    """
    alvo_lower = alvo.lower().strip()
    exe = PROGRAMAS.get(alvo_lower)
    try:
        if exe:
            subprocess.Popen(exe, shell=True)
            return "known"
        subprocess.Popen(f'start "" "{alvo}"', shell=True)
        return "attempted"
    except Exception as e:
        print(f"[ACAO] Erro ao abrir programa: {e}")
        return False


def parse_tempo(txt):
    """Converte '0:50', '1:20:05' ou '50' em segundos. Retorna 0 se inválido."""
    txt = (txt or "").strip()
    if not txt:
        return 0
    if ":" in txt:
        try:
            partes = [int(p) for p in txt.split(":")]
        except ValueError:
            return 0
        segundos = 0
        for p in partes:
            segundos = segundos * 60 + p
        return segundos
    try:
        return int(float(txt))
    except ValueError:
        return 0


def youtube_buscar_video(query):
    """Busca o primeiro vídeo pra essa query via YouTube Data API v3.
    Retorna o video_id, ou None se a chave não estiver configurada ou a busca falhar."""
    if not YOUTUBE_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "video",
                "maxResults": 1,
                "q": query,
                "key": YOUTUBE_API_KEY,
            },
            timeout=6,
        )
        data = resp.json()
        items = data.get("items", [])
        if items:
            return items[0]["id"]["videoId"]
    except Exception as e:
        print(f"[YOUTUBE] erro na busca: {e}")
    return None


def google_buscar_link(query):
    """Busca o primeiro resultado pra essa query via Google Custom Search API.
    Retorna a URL, ou None se as chaves não estiverem configuradas ou a busca falhar."""
    if not (GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID):
        return None
    try:
        resp = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": GOOGLE_CSE_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": query,
                "num": 1,
            },
            timeout=6,
        )
        data = resp.json()
        items = data.get("items", [])
        if items:
            return items[0]["link"]
    except Exception as e:
        print(f"[GOOGLE CSE] erro na busca: {e}")
    return None


def extrair_acoes_de_url(resposta_ia):
    acoes_frontend = []
    matches = re.findall(r"\[ACAO:\s*(.*?):\s*(.*?)\]", resposta_ia, re.IGNORECASE | re.DOTALL)

    for tipo, conteudo in matches:
        tipo = tipo.lower().strip()
        conteudo = conteudo.strip().strip('"').strip("`")

        if tipo in ("run", "abrir", "programa"):
            abrir_programa(conteudo)
        elif tipo in ("youtube", "yt"):
            import urllib.parse
            if conteudo.lower() in ("", "home", "youtube"):
                acoes_frontend.append({"type": "open", "url": "https://www.youtube.com"})
            else:
                url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(conteudo)}"
                acoes_frontend.append({"type": "open", "url": url})
        elif tipo == "google":
            import urllib.parse
            if conteudo.lower() in ("", "home", "google"):
                acoes_frontend.append({"type": "open", "url": "https://www.google.com"})
            else:
                url = f"https://www.google.com/search?q={urllib.parse.quote(conteudo)}"
                acoes_frontend.append({"type": "open", "url": url})
        elif tipo == "url":
            url = conteudo if conteudo.startswith("http") else f"https://{conteudo}"
            acoes_frontend.append({"type": "open", "url": url})
        elif tipo in ("youtube_video", "youtube_watch", "yt_video"):
            import urllib.parse
            if "@" in conteudo:
                query, tempo_str = conteudo.split("@", 1)
            else:
                query, tempo_str = conteudo, ""
            query = query.strip()
            segundos = parse_tempo(tempo_str)
            video_id = youtube_buscar_video(query)
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
                if segundos > 0:
                    url += f"&t={segundos}s"
            else:
                # Sem YOUTUBE_API_KEY configurada (ou a busca falhou): cai pra
                # página de resultados normal em vez de abrir um vídeo às ciegas.
                url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
            acoes_frontend.append({"type": "open", "url": url})
        elif tipo in ("abrirlink", "abrir_link", "link"):
            import urllib.parse
            url = google_buscar_link(conteudo)
            if not url:
                # Sem GOOGLE_CSE_API_KEY/GOOGLE_CSE_ID configuradas (ou busca
                # falhou): cai pra página de resultados normal do Google.
                url = f"https://www.google.com/search?q={urllib.parse.quote(conteudo)}"
            acoes_frontend.append({"type": "open", "url": url})

    texto_limpo = re.sub(r"\[ACAO:.*?\]", "", resposta_ia, flags=re.IGNORECASE | re.DOTALL).strip()
    return texto_limpo, acoes_frontend


# ==================== CHAMADAS DE API ====================

def chamar_groq(historico_completo):
    if not groq_client:
        raise RuntimeError("Groq não configurado")

    mensagens_api = [{"role": "system", "content": SYSTEM_PROMPT}]
    mensagens_api.extend(preparar_historico_para_api(historico_completo))

    completion = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=mensagens_api,
        temperature=0.8,
        max_tokens=800,
    )
    resposta = completion.choices[0].message.content.strip()
    estado["tokens_usados"] += estimar_tokens(resposta) + 1000
    return resposta


def chamar_gemini(user_input):
    if not gemini_client:
        raise RuntimeError("Gemini não configurado")

    response = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_input,
        config={
            "system_instruction": SYSTEM_PROMPT,
            "temperature": 0.7,
            "max_output_tokens": 800,
        },
    )
    return response.text.strip()


# ==================== ROTAS ====================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/conversations", methods=["GET"])
def api_list_conversations():
    device_id = request.args.get("device_id", "")
    if not device_id:
        return jsonify({"error": "device_id ausente"}), 400
    return jsonify({"conversations": listar_conversas(device_id)})


@app.route("/api/conversations", methods=["POST"])
def api_create_conversation():
    data = request.get_json(force=True) or {}
    device_id = data.get("device_id", "")
    if not device_id:
        return jsonify({"error": "device_id ausente"}), 400
    conv_id = criar_conversa(device_id)
    return jsonify({"id": conv_id, "titulo": "Nova conversa"})


@app.route("/api/conversations/<conv_id>/messages", methods=["GET"])
def api_conversation_messages(conv_id):
    device_id = request.args.get("device_id", "")
    if not conversa_pertence_ao_device(conv_id, device_id):
        return jsonify({"error": "conversa não encontrada"}), 404
    return jsonify({"messages": carregar_mensagens(conv_id)})


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def api_delete_conversation(conv_id):
    device_id = request.args.get("device_id", "")
    if not conversa_pertence_ao_device(conv_id, device_id):
        return jsonify({"error": "conversa não encontrada"}), 404
    deletar_conversa(conv_id)
    return jsonify({"ok": True})


@app.route("/api/conversations/<conv_id>", methods=["PATCH"])
def api_rename_conversation(conv_id):
    data = request.get_json(force=True) or {}
    device_id = data.get("device_id", "")
    if not conversa_pertence_ao_device(conv_id, device_id):
        return jsonify({"error": "conversa não encontrada"}), 404
    novo_titulo = (data.get("titulo") or "").strip()
    if not novo_titulo:
        return jsonify({"error": "título vazio"}), 400
    titulo_final = renomear_conversa(conv_id, novo_titulo)
    return jsonify({"ok": True, "titulo": titulo_final})


@app.route("/api/conversations/<conv_id>/pin", methods=["POST"])
def api_pin_conversation(conv_id):
    data = request.get_json(force=True) or {}
    device_id = data.get("device_id", "")
    if not conversa_pertence_ao_device(conv_id, device_id):
        return jsonify({"error": "conversa não encontrada"}), 404
    novo_estado = alternar_fixado(conv_id)
    return jsonify({"ok": True, "fixado": novo_estado})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    user_input = (data.get("message") or "").strip()
    conv_id = data.get("conversation_id")
    device_id = data.get("device_id", "")

    if not user_input:
        return jsonify({"error": "mensagem vazia"}), 400
    if not device_id:
        return jsonify({"error": "device_id ausente"}), 400

    if not conv_id or not conversa_pertence_ao_device(conv_id, device_id):
        conv_id = criar_conversa(device_id)

    primeira_mensagem = len(carregar_mensagens(conv_id)) == 0

    user_msg_id = salvar_mensagem(conv_id, "user", user_input)
    if primeira_mensagem:
        atualizar_titulo_se_necessario(conv_id, user_input)
    tocar_conversa(conv_id)

    historico = carregar_mensagens(conv_id)

    intent = classify_intent(user_input)
    local = resposta_local(intent, user_input)

    if local:
        resposta, acoes = local
        salvar_mensagem(conv_id, "assistant", resposta)
        return jsonify({
            "reply": resposta,
            "actions": acoes,
            "engine": "local",
            "conversation_id": conv_id,
            "user_message_id": user_msg_id,
            "tokens_usados": estado["tokens_usados"],
            "tokens_limite": estado["tokens_limite"],
        })

    # Gemini primeiro (mais capaz), Groq como reserva se o Gemini falhar.
    engine_usado = "gemini"
    try:
        resposta_ia = chamar_gemini(user_input)
    except Exception as e:
        print(f"[GEMINI] fallback -> Groq ({e})")
        engine_usado = "groq"
        try:
            if not tokens_disponiveis(5000):
                raise RuntimeError("orçamento de tokens baixo")
            resposta_ia = chamar_groq(historico)
        except Exception as e2:
            print(f"[GROQ] erro crítico: {e2}")
            resposta_ia = "Desculpe, senhor. Estou enfrentando dificuldades em meus servidores agora."
            engine_usado = "erro"

    texto_limpo, acoes = extrair_acoes_de_url(resposta_ia)
    salvar_mensagem(conv_id, "assistant", texto_limpo)

    return jsonify({
        "reply": texto_limpo,
        "actions": acoes,
        "engine": engine_usado,
        "conversation_id": conv_id,
        "user_message_id": user_msg_id,
        "tokens_usados": estado["tokens_usados"],
        "tokens_limite": estado["tokens_limite"],
    })


@app.route("/api/messages/<int:msg_id>/truncate", methods=["DELETE"])
def api_truncate_message(msg_id):
    """Apaga essa mensagem e todas as que vieram depois na mesma conversa.
    Usado quando o usuário EDITA uma mensagem antiga: a conversa é
    reconstruída a partir dali com o texto novo (via /api/chat de novo)."""
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id") or request.args.get("device_id", "")
    conv_id = truncar_a_partir_de(msg_id, device_id)
    if not conv_id:
        return jsonify({"error": "mensagem não encontrada"}), 404
    tocar_conversa(conv_id)
    return jsonify({"ok": True, "conversation_id": conv_id})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    device_id = request.form.get("device_id", "")
    if not device_id:
        return jsonify({"error": "device_id ausente"}), 400

    conv_id = request.form.get("conversation_id")
    if not conv_id or not conversa_pertence_ao_device(conv_id, device_id):
        conv_id = criar_conversa(device_id)

    if "file" not in request.files:
        return jsonify({"error": "nenhum arquivo enviado"}), 400

    f = request.files["file"]
    nome = f.filename or "arquivo"
    ext = os.path.splitext(nome)[1].lower()

    try:
        if ext == ".pdf" and PdfReader:
            reader = PdfReader(f.stream)
            texto = "\n".join([p.extract_text() or "" for p in reader.pages])
        elif ext == ".docx" and Document:
            doc = Document(f.stream)
            texto = "\n".join([p.text for p in doc.paragraphs])
        elif ext == ".txt":
            texto = f.stream.read().decode("utf-8", errors="ignore")
        else:
            return jsonify({"error": "formato não suportado (use .pdf, .docx ou .txt)"}), 400
    except Exception as e:
        return jsonify({"error": f"erro ao ler arquivo: {e}"}), 500

    trecho = texto[:3000]
    contexto = f"[ARQUIVO]\n{nome}\n\n{trecho}"
    salvar_mensagem(conv_id, "user", contexto)
    tocar_conversa(conv_id)

    return jsonify({"ok": True, "nome": nome, "preview": texto[:400], "conversation_id": conv_id})


if __name__ == "__main__":
    if not groq_client and not gemini_client:
        print("[AVISO] Nenhuma chave de API configurada. Crie um .env a partir do .env.example.")

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000")).start()

    # host="0.0.0.0" permite acessar de outros dispositivos na mesma rede Wi-Fi (ex: celular)
    app.run(debug=True, port=5000, host="0.0.0.0")
