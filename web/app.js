const statusEl = document.getElementById('status');
const portaEl = document.getElementById('porta');
const logEl = document.getElementById('log');
const modoDev = document.getElementById('modo-dev');
const devArea = document.getElementById('dev-area');
const listaGraficos = document.getElementById('lista-graficos');
const imagemGrande = document.getElementById('imagem-grande');

let logIndex = 0;
let abaAtual = 'ensaio';

function setStatus(msg, ok=true) {
  statusEl.textContent = msg;
  statusEl.className = ok ? 'status ok' : 'status erro';
}

async function carregarPortas() {
  const res = await fetch('/api/ports');
  const portas = await res.json();
  portaEl.innerHTML = '';
  portas.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p;
    opt.textContent = p;
    portaEl.appendChild(opt);
  });
}

async function statusConexao() {
  const res = await fetch('/api/status');
  const data = await res.json();
  setStatus(data.conectado ? 'Conectado' : 'Desconectado', data.conectado);
}

async function conectar() {
  const porta = portaEl.value;
  const res = await fetch('/api/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ porta })
  });
  const data = await res.json();
  setStatus(data.msg, data.ok);
}

async function desconectar() {
  await fetch('/api/disconnect', { method: 'POST' });
  setStatus('Desconectado', false);
}

async function enviar(comando) {
  const res = await fetch('/api/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comando })
  });
  const data = await res.json();
  if (!data.ok) {
    setStatus(data.msg, false);
  }
}

async function gerarGrafico() {
  const deslocamento = parseInt(document.getElementById('g-offset').value || '0', 10);
  const res = await fetch('/api/grafico', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ deslocamento })
  });
  const data = await res.json();
  setStatus(data.msg, data.ok);
  await atualizarGraficos();
}

async function rodarAnalise() {
  const res = await fetch('/api/analise', { method: 'POST' });
  const data = await res.json();
  setStatus(data.msg, data.ok);
  await atualizarGraficos();
}

async function encerrarServidor() {
  const res = await fetch('/api/shutdown', { method: 'POST' });
  const data = await res.json();
  setStatus(data.msg, data.ok);
}

async function atualizarLog() {
  const res = await fetch(`/api/log?desde=${logIndex}`);
  const data = await res.json();
  if (data.linhas && data.linhas.length) {
    const nearBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 50;
    logEl.textContent += data.linhas.join('\n') + '\n';
    if (nearBottom) logEl.scrollTop = logEl.scrollHeight;
  }
  logIndex = data.proximo || logIndex;
}

function criarItemGrafico(nome, base) {
  const item = document.createElement('button');
  item.className = 'arquivo';
  item.textContent = nome;
  item.addEventListener('click', () => {
    imagemGrande.src = `/files/${nome}`;
    imagemGrande.alt = nome;
  });
  return item;
}

async function atualizarGraficos() {
  const res = await fetch('/api/graficos');
  const data = await res.json();
  listaGraficos.innerHTML = '';
  let lista = [];
  if (abaAtual === 'ensaio') lista = data.graficos_ensaio || [];
  if (abaAtual === 'analise') lista = data.graficos_analise || [];
  if (abaAtual === 'resumo') lista = data.graficos_resumo || [];
  if (!lista.length) {
    listaGraficos.textContent = 'Nenhum gráfico encontrado.';
    return;
  }
  const grid = document.createElement('div');
  grid.className = 'lista';
  lista.forEach(nome => grid.appendChild(criarItemGrafico(nome)));
  listaGraficos.appendChild(grid);
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

  document.getElementById('btn-massa').addEventListener('click', () => {
    const valor = document.getElementById('massa').value;
    if (valor) enviar(`m ${valor}`);
  });

  document.getElementById('btn-lbc').addEventListener('click', () => {
    const valor = document.getElementById('lbc').value;
    if (valor) enviar(`lbc ${valor}`);
  });

  document.getElementById('btn-lbt').addEventListener('click', () => {
    const valor = document.getElementById('lbt').value;
    if (valor) enviar(`lbt ${valor}`);
  });

  document.getElementById('btn-u').addEventListener('click', () => {
    const valor = document.getElementById('up-ms').value;
    if (valor) enviar(`u ${valor}`);
  });

  document.getElementById('btn-j').addEventListener('click', () => {
    const valor = document.getElementById('down-ms').value;
    if (valor) enviar(`j ${valor}`);
  });

  document.getElementById('btn-g').addEventListener('click', gerarGrafico);
  document.getElementById('btn-analise').addEventListener('click', rodarAnalise);
  document.getElementById('btn-shutdown').addEventListener('click', encerrarServidor);
}

function registrarConexao() {
  document.getElementById('btn-atualizar').addEventListener('click', carregarPortas);
  document.getElementById('btn-conectar').addEventListener('click', conectar);
  document.getElementById('btn-desconectar').addEventListener('click', desconectar);
}

function registrarDev() {
  modoDev.addEventListener('change', () => {
    devArea.classList.toggle('oculto', !modoDev.checked);
  });
}

async function iniciar() {
  await carregarPortas();
  await statusConexao();
  await atualizarGraficos();
  registrarComandos();
  registrarConexao();
  registrarAba();
  registrarDev();
  document.getElementById('btn-atualizar-graficos').addEventListener('click', atualizarGraficos);
  setInterval(atualizarLog, 1000);
  setInterval(statusConexao, 2000);
}

iniciar();
