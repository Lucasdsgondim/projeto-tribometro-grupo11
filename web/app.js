const statusEl = document.getElementById('status');
const portaEl = document.getElementById('porta');
const logEl = document.getElementById('log');
const modoDev = document.getElementById('modo-dev');
const devArea = document.getElementById('dev-area');
const listaGraficos = document.getElementById('lista-graficos');
const imagemGrande = document.getElementById('imagem-grande');
const imgPlaceholder = document.getElementById('img-placeholder'); // Novo elemento

let logIndex = 0;
let abaAtual = 'ensaio';

function setStatus(msg, ok=true) {
  statusEl.textContent = msg;
  statusEl.className = ok ? 'status ok' : 'status erro';
}

async function carregarPortas() {
  try {
    const res = await fetch('/api/ports');
    const portas = await res.json();
    portaEl.innerHTML = '';

    if (portas.length === 0) {
      const opt = document.createElement('option');
      opt.textContent = "Nenhuma porta";
      portaEl.appendChild(opt);
      return;
    }

    portas.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p;
      opt.textContent = p;
      portaEl.appendChild(opt);
    });
  } catch (e) {
    console.error("Erro ao carregar portas:", e);
    portaEl.innerHTML = '<option>Erro API</option>';
  }
}

async function statusConexao() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    setStatus(data.conectado ? 'Conectado' : 'Desconectado', data.conectado);

    // Habilita/Desabilita botões baseado no status
    document.getElementById('btn-conectar').disabled = data.conectado;
    document.getElementById('btn-desconectar').disabled = !data.conectado;
  } catch (e) {
    setStatus('Erro de conexão', false);
  }
}

async function conectar() {
  const porta = portaEl.value;
  if (!porta) return;

  setStatus('Conectando...', true);
  try {
    const res = await fetch('/api/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ porta })
    });
    const data = await res.json();
    setStatus(data.msg, data.ok);
    statusConexao(); // Atualiza estado dos botões
  } catch (e) {
    setStatus('Falha ao conectar', false);
  }
}

async function desconectar() {
  try {
    await fetch('/api/disconnect', { method: 'POST' });
    setStatus('Desconectado', false);
    statusConexao();
  } catch (e) {
    console.error(e);
  }
}

async function enviar(comando) {
  try {
    const res = await fetch('/api/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comando })
    });
    const data = await res.json();
    if (!data.ok) {
      setStatus(data.msg, false);
    }
  } catch (e) {
    setStatus('Erro no envio', false);
  }
}

async function gerarGrafico() {
  const deslocamento = parseInt(document.getElementById('g-offset').value || '0', 10);
  setStatus('Gerando gráficos...', true);
  try {
    const res = await fetch('/api/grafico', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deslocamento })
    });
    const data = await res.json();
    setStatus(data.msg, data.ok);
    await atualizarGraficos();
  } catch (e) {
    setStatus('Erro ao gerar', false);
  }
}

async function rodarAnalise() {
  setStatus('Rodando análise...', true);
  try {
    const res = await fetch('/api/analise', { method: 'POST' });
    const data = await res.json();
    setStatus(data.msg, data.ok);
    await atualizarGraficos();
  } catch (e) {
    setStatus('Erro na análise', false);
  }
}

async function encerrarServidor() {
  if(!confirm("Tem certeza que deseja desligar o servidor?")) return;
  try {
    const res = await fetch('/api/shutdown', { method: 'POST' });
    const data = await res.json();
    setStatus(data.msg, data.ok);
  } catch (e) {
    console.error(e);
  }
}

async function atualizarLog() {
  try {
    const res = await fetch(`/api/log?desde=${logIndex}`);
    const data = await res.json();
    if (data.linhas && data.linhas.length) {
      const nearBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 50;
      logEl.textContent += data.linhas.join('\n') + '\n';
      if (nearBottom) logEl.scrollTop = logEl.scrollHeight;
    }
    logIndex = data.proximo || logIndex;
  } catch (e) {
    // Silencia erros de log para não poluir console
  }
}

function criarItemGrafico(nome, base) {
  // Alterado de 'button' para 'div' para evitar estilos de botão padrão (cinza/centralizado)
  const item = document.createElement('div');
  item.className = 'arquivo';
  item.textContent = nome;

  item.addEventListener('click', () => {
    // Atualiza a imagem
    imagemGrande.src = `/files/${nome}`;
    imagemGrande.alt = nome;

    // IMPORTANTE: Torna a imagem visível e esconde o placeholder
    imagemGrande.style.display = 'block';
    if(imgPlaceholder) imgPlaceholder.style.display = 'none';

    // Feedback visual de seleção na lista
    document.querySelectorAll('.arquivo').forEach(i => i.style.background = '');
    item.style.background = '#e2e8f0';
  });

  return item;
}

async function atualizarGraficos() {
  try {
    const res = await fetch('/api/graficos');
    const data = await res.json();
    listaGraficos.innerHTML = '';

    let lista = [];
    if (abaAtual === 'ensaio') lista = data.graficos_ensaio || [];
    if (abaAtual === 'analise') lista = data.graficos_analise || [];
    if (abaAtual === 'resumo') lista = data.graficos_resumo || [];

    if (!lista.length) {
      listaGraficos.innerHTML = '<div style="padding:10px; color:#666;">Nenhum gráfico encontrado.</div>';
      return;
    }

    const grid = document.createElement('div');
    grid.className = 'lista';
    lista.forEach(nome => grid.appendChild(criarItemGrafico(nome)));
    listaGraficos.appendChild(grid);
  } catch (e) {
    console.error("Erro ao atualizar gráficos", e);
  }
}

function registrarAba() {
  document.querySelectorAll('.aba').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.aba').forEach(b => b.classList.remove('ativa'));
      btn.classList.add('ativa');
      abaAtual = btn.dataset.aba;
      atualizarGraficos();
    });
  });
}

function registrarComandos() {
  document.querySelectorAll('[data-cmd]').forEach(btn => {
    btn.addEventListener('click', () => enviar(btn.dataset.cmd));
  });

  document.getElementById('btn-massa')?.addEventListener('click', () => {
    const valor = document.getElementById('massa').value;
    if (valor) enviar(`m ${valor}`);
  });

  document.getElementById('btn-lbc')?.addEventListener('click', () => {
    const valor = document.getElementById('lbc').value;
    if (valor) enviar(`lbc ${valor}`);
  });

  document.getElementById('btn-lbt')?.addEventListener('click', () => {
    const valor = document.getElementById('lbt').value;
    if (valor) enviar(`lbt ${valor}`);
  });

  document.getElementById('btn-u')?.addEventListener('click', () => {
    const valor = document.getElementById('up-ms').value;
    if (valor) enviar(`u ${valor}`);
  });

  document.getElementById('btn-j')?.addEventListener('click', () => {
    const valor = document.getElementById('down-ms').value;
    if (valor) enviar(`j ${valor}`);
  });

  document.getElementById('btn-g')?.addEventListener('click', gerarGrafico);
  document.getElementById('btn-analise')?.addEventListener('click', rodarAnalise);
  document.getElementById('btn-shutdown')?.addEventListener('click', encerrarServidor);
}

function registrarConexao() {
  document.getElementById('btn-atualizar')?.addEventListener('click', carregarPortas);
  document.getElementById('btn-conectar')?.addEventListener('click', conectar);
  document.getElementById('btn-desconectar')?.addEventListener('click', desconectar);
}

function registrarDev() {
  if(modoDev) {
    modoDev.addEventListener('change', () => {
      devArea.classList.toggle('oculto', !modoDev.checked);
    });
  }
}

async function iniciar() {
  await carregarPortas();
  await statusConexao();
  await atualizarGraficos();
  registrarComandos();
  registrarConexao();
  registrarAba();
  registrarDev();
  document.getElementById('btn-atualizar-graficos')?.addEventListener('click', atualizarGraficos);

  // Loops de atualização
  setInterval(atualizarLog, 1000);
  setInterval(statusConexao, 2000);
}

// Inicia a aplicação
iniciar();
