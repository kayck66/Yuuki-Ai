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

function getDeviceId(){
  let id = localStorage.getItem('yuuki_device_id');
  if(!id){
    id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
    localStorage.setItem('yuuki_device_id', id);
  }
  return id;
}
const DEVICE_ID = getDeviceId();

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

// ==================== RENDERIZAÇÃO DE MARKDOWN ====================
// Converte markdown simples (negrito, títulos, listas) em HTML seguro.
// Escapamos o texto primeiro (evita XSS) e só depois aplicamos as tags.

function escapeHtml(text){
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function renderMarkdown(text){
  let escaped = escapeHtml(text);
  const linhas = escaped.split('\n');
  const partes = [];
  let listaAberta = null; // 'ul' | 'ol' | null

  const fecharLista = () => {
    if(listaAberta){
      partes.push(listaAberta === 'ul' ? '</ul>' : '</ol>');
      listaAberta = null;
    }
  };

  for(let linha of linhas){
    const linhaTrim = linha.trim();

    const tituloMatch = linhaTrim.match(/^(#{1,4})\s+(.*)/);
    const bulletMatch = linhaTrim.match(/^[-*]\s+(.*)/);
    const numeradaMatch = linhaTrim.match(/^\d+[.)]\s+(.*)/);

    const aplicarInline = (s) => {
      // negrito **texto**
      s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      // itálico *texto* (só quando não faz parte de **)
      s = s.replace(/(^|[^*])\*([^*]+)\*([^*]|$)/g, '$1<em>$2</em>$3');
      // código `texto`
      s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
      return s;
    };

    if(tituloMatch){
      fecharLista();
      const nivel = Math.min(tituloMatch[1].length + 2, 6); // h3..h6
      partes.push(`<h${nivel} class="md-heading">${aplicarInline(tituloMatch[2])}</h${nivel}>`);
    } else if(bulletMatch){
      if(listaAberta !== 'ul'){ fecharLista(); partes.push('<ul class="md-list">'); listaAberta = 'ul'; }
      partes.push(`<li>${aplicarInline(bulletMatch[1])}</li>`);
    } else if(numeradaMatch){
      if(listaAberta !== 'ol'){ fecharLista(); partes.push('<ol class="md-list">'); listaAberta = 'ol'; }
      partes.push(`<li>${aplicarInline(numeradaMatch[1])}</li>`);
    } else if(linhaTrim === ''){
      fecharLista();
      partes.push('<div class="md-spacer"></div>');
    } else {
      fecharLista();
      partes.push(`<p class="md-p">${aplicarInline(linha)}</p>`);
    }
  }
  fecharLista();
  return partes.join('');
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
  if(role === 'user'){
    // Mensagens do usuário ficam como texto puro (não precisam de formatação
    // e evita qualquer ambiguidade sobre o que o usuário "quis dizer" com * ou #).
    bubble.textContent = text;
  } else {
    // Respostas da Yuuki são renderizadas como markdown (negrito, títulos, listas).
    bubble.innerHTML = renderMarkdown(text);
  }

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
    addMessage('yuuki', 'Espera a resposta terminar antes de editar essa mensagem.');
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
      const res = await fetch(`/api/messages/${msgId}/truncate`, {
        method: 'DELETE',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({device_id: DEVICE_ID})
      });
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
      body: JSON.stringify({message: text, conversation_id: currentConversationId, device_id: DEVICE_ID})
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
  form.append('device_id', DEVICE_ID);
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
      addMessage('yuuki', `Arquivo "${data.nome}" recebido. Já está no meu contexto.`);
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

const MENU_DOTS_SVG = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M12 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"/></svg>`;
const SHARE_SVG = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M18 16.08a3 3 0 0 0-2.11.87L8.91 12.7a3 3 0 0 0 0-1.4l6.98-4.25A3 3 0 1 0 15 5a3 3 0 0 0 .05.55L8.07 9.8a3 3 0 1 0 0 4.4l6.98 4.25A3 3 0 1 0 18 16.08z"/></svg>`;
const PIN_SVG = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M16 3l5 5-3.5 3.5L19 14l-1.4 1.4-3.1-3.1-3.9 3.9V21h-1.2l-.5-5.2L5 12.7l1.4-1.4 3.1 3.1 3.9-3.9-3.1-3.1L11.7 6l1.9 1.9L16 3z"/></svg>`;
const RENAME_SVG = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M3 17.25V21h3.75L20.81 6.94l-3.75-3.75L3 17.25z"/></svg>`;
const NOTEBOOK_SVG = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h13v-2H6v-1h13V4H6zm0 2h2v9l-1-.75L6 13V4z"/></svg>`;
const TRASH_SVG = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M9 3h6l1 2h4v2H4V5h4l1-2zm-2 6h10l-1 12H8L7 9z"/></svg>`;

let openMenuEl = null;

function closeConversationMenu(){
  if(openMenuEl){
    openMenuEl.remove();
    openMenuEl = null;
  }
  document.querySelectorAll('.conversation-item.menu-open').forEach(el => el.classList.remove('menu-open'));
}
document.addEventListener('click', (e) => {
  if(openMenuEl && !openMenuEl.contains(e.target) && !e.target.closest('.conversation-menu-btn')){
    closeConversationMenu();
  }
});

function openConversationMenu(anchorBtn, item, conv){
  closeConversationMenu();
  item.classList.add('menu-open');

  const menu = document.createElement('div');
  menu.className = 'conversation-menu';

  const rect = anchorBtn.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 4}px`;
  menu.style.left = `${Math.max(8, rect.right - 210)}px`;

  const opcoes = [
    { label: 'Exportar conversa', icon: SHARE_SVG, action: () => exportConversation(conv) },
    { label: conv.fixado ? 'Desafixar' : 'Fixar', icon: PIN_SVG, action: () => togglePinConversation(conv, item) },
    { label: 'Renomear', icon: RENAME_SVG, action: () => renameConversationInline(item, conv) },
    { label: 'Adicionar ao notebook', icon: NOTEBOOK_SVG, disabled: true, title: 'Notebooks ainda não implementado nesta versão' },
    { divider: true },
    { label: 'Excluir', icon: TRASH_SVG, danger: true, action: () => deleteConversation(conv) },
  ];

  opcoes.forEach(op => {
    if(op.divider){
      const div = document.createElement('div');
      div.className = 'conversation-menu-divider';
      menu.appendChild(div);
      return;
    }
    const btn = document.createElement('button');
    btn.className = 'conversation-menu-item' + (op.danger ? ' danger' : '') + (op.disabled ? ' disabled' : '');
    btn.innerHTML = op.icon + `<span>${op.label}</span>`;
    if(op.title) btn.title = op.title;
    if(!op.disabled){
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        closeConversationMenu();
        op.action();
      });
    }
    menu.appendChild(btn);
  });

  document.body.appendChild(menu);
  openMenuEl = menu;
}

async function togglePinConversation(conv, item){
  try{
    const res = await fetch(`/api/conversations/${conv.id}/pin`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({device_id: DEVICE_ID})
    });
    const data = await res.json();
    if(!data.error) await loadConversationList();
  } catch(err){
    console.error('Falha ao fixar conversa', err);
  }
}

function renameConversationInline(item, conv){
  const titleEl = item.querySelector('.conversation-title');
  const input = document.createElement('input');
  input.className = 'conversation-rename-input';
  input.value = conv.titulo;
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  const confirmar = async () => {
    const novoTitulo = input.value.trim();
    if(novoTitulo && novoTitulo !== conv.titulo){
      try{
        await fetch(`/api/conversations/${conv.id}`, {
          method: 'PATCH',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({titulo: novoTitulo, device_id: DEVICE_ID})
        });
      } catch(err){
        console.error('Falha ao renomear', err);
      }
    }
    loadConversationList();
  };

  input.addEventListener('keydown', (e) => {
    if(e.key === 'Enter') input.blur();
    if(e.key === 'Escape'){ input.value = conv.titulo; input.blur(); }
  });
  input.addEventListener('blur', confirmar);
}

async function exportConversation(conv){
  try{
    const res = await fetch(`/api/conversations/${conv.id}/messages?device_id=${DEVICE_ID}`);
    const data = await res.json();
    const linhas = (data.messages || [])
      .filter(m => !m.content.startsWith('[ARQUIVO]'))
      .map(m => `${m.role === 'user' ? 'Você' : 'Yuuki'}: ${m.content}`);
    const texto = `${conv.titulo}\n\n${linhas.join('\n\n')}`;
    await navigator.clipboard.writeText(texto);
    addMessage('yuuki', `Copiei a conversa "${conv.titulo}" pra sua área de transferência.`);
  } catch(err){
    addMessage('yuuki', 'Não consegui exportar essa conversa.');
  }
}

async function deleteConversation(conv){
  const confirmado = confirm(`Excluir a conversa "${conv.titulo}"? Isso não pode ser desfeito.`);
  if(!confirmado) return;

  try{
    await fetch(`/api/conversations/${conv.id}?device_id=${DEVICE_ID}`, { method: 'DELETE' });
    if(conv.id === currentConversationId){
      setConversationId(null);
      messagesEl.innerHTML = '';
      emptyState.style.display = 'block';
      setEngineStatus(null);
    }
    loadConversationList();
  } catch(err){
    console.error('Falha ao excluir conversa', err);
  }
}

function renderConversationList(filtro = ''){
  closeConversationMenu();
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
    item.className = 'conversation-item'
      + (conv.id === currentConversationId ? ' active' : '')
      + (conv.fixado ? ' pinned' : '');

    const title = document.createElement('span');
    title.className = 'conversation-title';
    title.textContent = conv.titulo;
    title.title = conv.titulo;
    title.addEventListener('click', () => switchConversation(conv.id));

    const menuBtn = document.createElement('button');
    menuBtn.className = 'conversation-menu-btn';
    menuBtn.innerHTML = MENU_DOTS_SVG;
    menuBtn.title = 'Mais opções';
    menuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openConversationMenu(menuBtn, item, conv);
    });

    item.appendChild(title);
    item.appendChild(menuBtn);
    conversationList.appendChild(item);
  });
}

async function loadConversationList(){
  try{
    const res = await fetch(`/api/conversations?device_id=${DEVICE_ID}`);
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
    const res = await fetch(`/api/conversations/${id}/messages?device_id=${DEVICE_ID}`);
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
