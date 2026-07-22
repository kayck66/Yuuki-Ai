const chatScroll = document.getElementById('chatScroll');
const messagesEl = document.getElementById('messages');
const emptyState = document.getElementById('emptyState');
const input = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const fileInput = document.getElementById('fileInput');
const newChatBtn = document.getElementById('newChatBtn');
const brandCore = document.getElementById('brandCore').querySelector('svg');
const engineDot = document.getElementById('engineDot');
const engineLabel = document.getElementById('engineLabel');
const engineDotComposer = document.getElementById('engineDotComposer');
const engineLabelComposer = document.getElementById('engineLabelComposer');
const tokenBarFill = document.getElementById('tokenBarFill');
const tokenText = document.getElementById('tokenText');
const sidebar = document.getElementById('sidebar');
const menuBtn = document.getElementById('menuBtn');
const drawerClose = document.getElementById('drawerClose');
const drawerOverlay = document.getElementById('drawerOverlay');
const searchInput = document.getElementById('searchInput');
const conversationList = document.getElementById('conversationList');
const conversationEmpty = document.getElementById('conversationEmpty');

const CORE_SVG = `
  <svg viewBox="0 0 24 24" class="core-svg"><circle class="ring ring-outer" cx="12" cy="12" r="10.2"/><circle class="ring ring-mid" cx="12" cy="12" r="7"/><circle class="ring ring-inner" cx="12" cy="12" r="3.2"/></svg>
`;

const COPY_SVG = `<svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z"/></svg>`;
const EDIT_SVG = `<svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M3 17.25V21h3.75L20.81 6.94l-3.75-3.75L3 17.25zM20.71 5.63a1 1 0 0 0 0-1.42l-2.92-2.92a1 1 0 0 0-1.42 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>`;
const CHECK_SVG = `<svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"/></svg>`;

let currentConversationId = localStorage.getItem('yuuki_conversation_id') || null;
let allConversations = [];

function scrollToBottom(){
  chatScroll.scrollTop = chatScroll.scrollHeight;
}

function setEngineStatus(engine){
  [ [engineDot, engineLabel], [engineDotComposer, engineLabelComposer] ].forEach(([dot, label]) => {
    dot.classList.remove('active', 'error');
    if(engine === 'erro'){
      dot.classList.add('error');
      label.textContent = 'erro';
    } else if(engine){
      dot.classList.add('active');
      label.textContent = engine;
    } else {
      label.textContent = 'aguardando';
    }
  });
}

function updateTokenBar(usados, limite){
  const pct = limite > 0 ? Math.min(100, (usados / limite) * 100) : 0;
  tokenBarFill.style.width = pct + '%';
  tokenText.textContent = `${usados.toLocaleString('pt-BR')} / ${limite.toLocaleString('pt-BR')} tokens`;
}

function addMessage(role, text, id = null){
  emptyState.style.display = 'none';
  const row = document.createElement('div');
  row.className = `msg-row ${role === 'user' ? 'user' : 'yuuki'}`;
  row.dataset.msgId = id || '';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  if(role !== 'user') avatar.innerHTML = CORE_SVG;
  row.appendChild(avatar);

  const wrap = document.createElement('div');
  buildMessageContent(wrap, role, text);
  row.appendChild(wrap);

  messagesEl.appendChild(row);
  scrollToBottom();
  return row;
}

function buildMessageContent(wrap, role, text){
  wrap.innerHTML = '';

  const name = document.createElement('div');
  name.className = 'msg-name';
  name.textContent = role === 'user' ? 'você' : 'yuuki';

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.textContent = text;

  const actions = document.createElement('div');
  actions.className = 'msg-actions';

  const copyBtn = document.createElement('button');
  copyBtn.className = 'msg-action-btn';
  copyBtn.title = 'Copiar';
  copyBtn.innerHTML = COPY_SVG;
  copyBtn.addEventListener('click', () => copyMessageText(bubble.textContent, copyBtn));
  actions.appendChild(copyBtn);

  if(role === 'user'){
    const editBtn = document.createElement('button');
    editBtn.className = 'msg-action-btn';
    editBtn.title = 'Editar';
    editBtn.innerHTML = EDIT_SVG;
    editBtn.addEventListener('click', () => {
      const row = wrap.closest('.msg-row');
      startEditMessage(row, wrap, text);
    });
    actions.appendChild(editBtn);
  }

  wrap.appendChild(name);
  wrap.appendChild(bubble);
  wrap.appendChild(actions);
}

function copyMessageText(text, btn){
  navigator.clipboard.writeText(text).then(() => {
    const original = btn.innerHTML;
    btn.classList.add('copied');
    btn.innerHTML = CHECK_SVG;
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = original;
    }, 1200);
  }).catch(() => {});
}

function startEditMessage(row, wrap, originalText){
  const msgId = row.dataset.msgId;
  if(!msgId){
    addMessage('yuuki', 'Espera a resposta terminar antes de editar essa mensagem, querido.');
    return;
  }

  wrap.innerHTML = '';
  const editBox = document.createElement('div');
  editBox.className = 'msg-edit-box';

  const textarea = document.createElement('textarea');
  textarea.className = 'msg-edit-textarea';
  textarea.value = originalText;

  const editActions = document.createElement('div');
  editActions.className = 'msg-edit-actions';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'msg-edit-btn';
  cancelBtn.textContent = 'Cancelar';
  cancelBtn.addEventListener('click', () => buildMessageContent(wrap, 'user', originalText));

  const saveBtn = document.createElement('button');
  saveBtn.className = 'msg-edit-btn primary';
  saveBtn.textContent = 'Salvar e reenviar';
  saveBtn.addEventListener('click', async () => {
    const newText = textarea.value.trim();
    if(!newText) return;
    saveBtn.disabled = true;
    cancelBtn.disabled = true;

    try{
      const res = await fetch(`/api/messages/${msgId}/truncate`, { method: 'DELETE' });
      const data = await res.json();
      if(data.error){
        addMessage('yuuki', 'Não consegui editar essa mensagem: ' + data.error);
        return;
      }
      let node = row;
      while(node){
        const next = node.nextSibling;
        node.remove();
        node = next;
      }
      input.value = newText;
      await sendMessage();
    } catch(err){
      addMessage('yuuki', 'Falha ao editar a mensagem.');
    }
  });

  editActions.appendChild(cancelBtn);
  editActions.appendChild(saveBtn);
  editBox.appendChild(textarea);
  editBox.appendChild(editActions);
  wrap.appendChild(editBox);
  textarea.focus();
}

function addThinkingRow(){
  const row = document.createElement('div');
  row.className = 'msg-row yuuki thinking-row';
  row.id = 'thinkingRow';

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.innerHTML = CORE_SVG;
  avatar.querySelector('.core-svg').classList.add('thinking');
  row.appendChild(avatar);

  const wrap = document.createElement('div');
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.textContent = 'processando...';
  wrap.appendChild(bubble);
  row.appendChild(wrap);

  messagesEl.appendChild(row);
  scrollToBottom();
}

function removeThinkingRow(){
  const row = document.getElementById('thinkingRow');
  if(row) row.remove();
}

function executeActions(actions){
  if(!actions) return;
  actions.forEach(a => {
    if(a.type === 'open' && a.url){
      window.open(a.url, '_blank');
    }
  });
}

function setConversationId(id){
  currentConversationId = id;
  if(id){
    localStorage.setItem('yuuki_conversation_id', id);
  } else {
    localStorage.removeItem('yuuki_conversation_id');
  }
}

// ==================== ENVIO DE MENSAGEM ====================

async function sendMessage(){
  const text = input.value.trim();
  if(!text) return;

  const userRow = addMessage('user', text);
  input.value = '';
  sendBtn.disabled = true;
  brandCore.classList.add('thinking');
  addThinkingRow();

  try{
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, conversation_id: currentConversationId})
    });
    const data = await res.json();

    removeThinkingRow();

    if(data.error){
      addMessage('yuuki', 'Algo deu errado: ' + data.error);
    } else {
      if(data.user_message_id){
        userRow.dataset.msgId = data.user_message_id;
      }
      addMessage('yuuki', data.reply || '...');
      executeActions(data.actions);
      setEngineStatus(data.engine);
      updateTokenBar(data.tokens_usados || 0, data.tokens_limite || 100000);
      if(data.conversation_id && data.conversation_id !== currentConversationId){
        setConversationId(data.conversation_id);
      }
      loadConversationList();
    }
  } catch(err){
    removeThinkingRow();
    addMessage('yuuki', 'Não consegui falar com o servidor. Ele está rodando?');
    setEngineStatus('erro');
  } finally {
    sendBtn.disabled = false;
    brandCore.classList.remove('thinking');
    input.focus();
  }
}

sendBtn.addEventListener('click', sendMessage);
input.addEventListener('keydown', e => {
  if(e.key === 'Enter') sendMessage();
});

// ==================== UPLOAD DE ARQUIVO ====================

fileInput.addEventListener('change', async () => {
  const file = fileInput.files[0];
  if(!file) return;

  const form = new FormData();
  form.append('file', file);
  if(currentConversationId) form.append('conversation_id', currentConversationId);

  try{
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    if(data.error){
      addMessage('yuuki', 'Não consegui ler esse arquivo: ' + data.error);
    } else {
      if(data.conversation_id && data.conversation_id !== currentConversationId){
        setConversationId(data.conversation_id);
      }
      addMessage('yuuki', `Arquivo "${data.nome}" recebido, senhor. Já está no meu contexto. ✨`);
      loadConversationList();
    }
  } catch(err){
    addMessage('yuuki', 'Falha ao enviar o arquivo.');
  } finally {
    fileInput.value = '';
  }
});

// ==================== DRAWER MOBILE ====================

function openDrawer(){
  sidebar.classList.add('open');
  drawerOverlay.classList.add('open');
}
function closeDrawer(){
  sidebar.classList.remove('open');
  drawerOverlay.classList.remove('open');
}
menuBtn.addEventListener('click', openDrawer);
drawerClose.addEventListener('click', closeDrawer);
drawerOverlay.addEventListener('click', closeDrawer);

// ==================== CONVERSAS (nova / lista / busca / trocar) ====================

function renderConversationList(filtro = ''){
  conversationList.innerHTML = '';
  const termo = filtro.trim().toLowerCase();
  const filtradas = termo
    ? allConversations.filter(c => c.titulo.toLowerCase().includes(termo))
    : allConversations;

  if(filtradas.length === 0){
    conversationEmpty.style.display = 'block';
    conversationList.appendChild(conversationEmpty);
    return;
  }
  conversationEmpty.style.display = 'none';

  filtradas.forEach(conv => {
    const item = document.createElement('div');
    item.className = 'conversation-item' + (conv.id === currentConversationId ? ' active' : '');
    item.textContent = conv.titulo;
    item.title = conv.titulo;
    item.addEventListener('click', () => switchConversation(conv.id));
    conversationList.appendChild(item);
  });
}

async function loadConversationList(){
  try{
    const res = await fetch('/api/conversations');
    const data = await res.json();
    allConversations = data.conversations || [];
    renderConversationList(searchInput.value);
  } catch(err){
    console.error('Falha ao carregar lista de conversas', err);
  }
}

async function switchConversation(id){
  setConversationId(id);
  messagesEl.innerHTML = '';
  emptyState.style.display = 'none';

  try{
    const res = await fetch(`/api/conversations/${id}/messages`);
    const data = await res.json();
    (data.messages || []).forEach(msg => {
      if(msg.content.startsWith('[ARQUIVO]')) return;
      addMessage(msg.role === 'user' ? 'user' : 'yuuki', msg.content, msg.id);
    });
  } catch(err){
    console.error('Falha ao carregar mensagens da conversa', err);
  }

  renderConversationList(searchInput.value);
  closeDrawer();
}

newChatBtn.addEventListener('click', () => {
  setConversationId(null);
  messagesEl.innerHTML = '';
  emptyState.style.display = 'block';
  setEngineStatus(null);
  renderConversationList(searchInput.value);
  closeDrawer();
  input.focus();
});

searchInput.addEventListener('input', () => renderConversationList(searchInput.value));

// ==================== INICIALIZAÇÃO ====================

async function init(){
  await loadConversationList();

  if(currentConversationId){
    const existe = allConversations.some(c => c.id === currentConversationId);
    if(existe){
      await switchConversation(currentConversationId);
    } else {
      setConversationId(null);
    }
  }

  updateTokenBar(0, 100000);
}

init();
input.focus();
