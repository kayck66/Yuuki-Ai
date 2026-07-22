import os
import re
import uuid
import sqlite3
import subprocess
import threading
import webbrowser
from datetime import datetime

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

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
    "AÇÕES (use APENAS se pedido explicitamente pelo usuário):\n"
    "- [ACAO: run: programa]\n"
    "- [ACAO: google: termo]\n"
    "- [ACAO: youtube: termo]\n"
    "- [ACAO: url: site]\n"
)

MAX_TOKENS_API = 2000
MAX_MENSAGENS_HISTORICO = 8
TOKENS_POR_PALAVRA = 1.3

estado = {
    "tokens_usados": 0,
    "tokens_limite": 100000,
}

PROGRAMAS = {
    "calculadora": "calc.exe", "calc": "calc.exe",
    "bloco de notas": "notepad.exe", "notepad": "notepad.exe", "bloco": "notepad.exe",
    "paint": "mspaint.exe", "cmd": "cmd.exe",
    "chrome": "chrome.exe", "edge": "msedge.exe", "vscode": "Code.exe",
    "discord": "Discord.exe", "spotify": "Spotify.exe", "explorer": "explorer.exe",
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
            fixado INTEGER DEFAULT 0
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
    # Migração: se o banco já existia antes da coluna 'fixado' existir, adiciona agora.
    try:
        conn.execute("ALTER TABLE conversas ADD COLUMN fixado INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # coluna já existe
    conn.commit()
    return conn


def criar_conversa(titulo="Nova conversa"):
    conv_id = uuid.uuid4().hex[:12]
    agora = datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO conversas (id, titulo, created_at, updated_at, fixado) VALUES (?, ?, ?, ?, 0)",
        (conv_id, titulo, agora, agora),
    )
    conn.commit()
    conn.close()
    return conv_id


def conversa_existe(conv_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM conversas WHERE id = ?", (conv_id,)).fetchone()
    conn.close()
    return row is not None


def listar_conversas():
    conn = get_conn()
    cursor = conn.execute(
        "SELECT id, titulo, updated_at, fixado FROM conversas ORDER BY fixado DESC, updated_at DESC"
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


def truncar_a_partir_de(msg_id):
    """Apaga a mensagem msg_id e tudo que veio depois dela na mesma conversa
    (usado quando o usuário edita uma mensagem antiga: a partir dali, a
    conversa é reconstruída com o texto novo)."""
    conn = get_conn()
    row = conn.execute("SELECT conversation_id FROM mensagens WHERE id = ?", (msg_id,)).fetchone()
    if not row:
        conn.close()
        return None
    conv_id = row[0]
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
    patterns = {
        "abrir_programa": [r"\b(abra?|abre|me abre|open)\b.*\b(calc|bloco|notepad|paint|discord|spotify|chrome|edge|vscode|cmd|explorer)\b"],
        "pesquisar": [r"\b(pesquise?|busque|google|youtube)\b"],
        "conversa": [r"^\s*(oi|ol[áa]|opa|hey|tudo bem)\s*[!?.]*\s*$"],
    }
    for intent, regexes in patterns.items():
        for regex in regexes:
            if re.search(regex, user_lower):
                return intent
    return "conversa"


def resposta_local(intent, user_input):
    if intent == "abrir_programa":
        match = re.search(
            r"\b(calc|bloco|notepad|paint|discord|spotify|chrome|edge|vscode|cmd|explorer)\b",
            user_input.lower(),
        )
        if match:
            programa = match.group(1)
            resultado = abrir_programa(programa)
            nomes = {"calc": "calculadora", "bloco": "bloco de notas", "notepad": "bloco de notas"}
            nome = nomes.get(programa, programa)
            if resultado:
                return f"Abrindo {nome} para você, querido. ✨", []
            return f"Tentei abrir {nome}, mas não consegui encontrá-lo por aqui, meu bem.", []

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
    alvo_lower = alvo.lower().strip()
    exe = PROGRAMAS.get(alvo_lower)
    try:
        if exe:
            subprocess.Popen(exe, shell=True)
            return True
        subprocess.Popen(f'start "" "{alvo}"', shell=True)
        return True
    except Exception as e:
        print(f"[ACAO] Erro ao abrir programa: {e}")
        return False


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
    return jsonify({"conversations": listar_conversas()})


@app.route("/api/conversations", methods=["POST"])
def api_create_conversation():
    conv_id = criar_conversa()
    return jsonify({"id": conv_id, "titulo": "Nova conversa"})


@app.route("/api/conversations/<conv_id>/messages", methods=["GET"])
def api_conversation_messages(conv_id):
    if not conversa_existe(conv_id):
        return jsonify({"error": "conversa não encontrada"}), 404
    return jsonify({"messages": carregar_mensagens(conv_id)})


@app.route("/api/conversations/<conv_id>", methods=["DELETE"])
def api_delete_conversation(conv_id):
    deletar_conversa(conv_id)
    return jsonify({"ok": True})


@app.route("/api/conversations/<conv_id>", methods=["PATCH"])
def api_rename_conversation(conv_id):
    if not conversa_existe(conv_id):
        return jsonify({"error": "conversa não encontrada"}), 404
    data = request.get_json(force=True) or {}
    novo_titulo = (data.get("titulo") or "").strip()
    if not novo_titulo:
        return jsonify({"error": "título vazio"}), 400
    titulo_final = renomear_conversa(conv_id, novo_titulo)
    return jsonify({"ok": True, "titulo": titulo_final})


@app.route("/api/conversations/<conv_id>/pin", methods=["POST"])
def api_pin_conversation(conv_id):
    novo_estado = alternar_fixado(conv_id)
    if novo_estado is None:
        return jsonify({"error": "conversa não encontrada"}), 404
    return jsonify({"ok": True, "fixado": novo_estado})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True) or {}
    user_input = (data.get("message") or "").strip()
    conv_id = data.get("conversation_id")

    if not user_input:
        return jsonify({"error": "mensagem vazia"}), 400

    if not conv_id or not conversa_existe(conv_id):
        conv_id = criar_conversa()

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
    conv_id = truncar_a_partir_de(msg_id)
    if not conv_id:
        return jsonify({"error": "mensagem não encontrada"}), 404
    tocar_conversa(conv_id)
    return jsonify({"ok": True, "conversation_id": conv_id})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    conv_id = request.form.get("conversation_id")
    if not conv_id or not conversa_existe(conv_id):
        conv_id = criar_conversa()

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

    app.run(debug=True, port=5000, host="0.0.0.0")
