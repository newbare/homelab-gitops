/* ==========================================================================
   Calculadora Resilience — front-end

   Duas regras que valem registrar, porque são decisões e não estilo:

   1. A CONTA NÃO ACONTECE AQUI. O front só desenha o que `/api/calcular`
      devolve. Duas implementações da mesma soma é como dois números
      diferentes nascem — e o do navegador seria o que ninguém audita.

   2. SEM CDN, SEM DEPENDÊNCIA. Nada de chart.js, nada de fonte externa.
      As barras são CSS. O cluster pode estar sem saída para a internet e o
      painel continua funcionando — e não há cadeia de terceiros para
      comprometer um painel que fala de custo.
   ========================================================================== */

'use strict';

const estado = { horas: 168, dados: null, expandidos: new Set(), modelo: null, descoberta: null };

/* --------------------------------------------------------------------------
   STACK DECLARADA — a lista que vira os selos da página.

   A coluna `nota` é a que interessa: ela diz o que a peça É e o que NÃO é.
   "JavaScript puro — sem React" informa mais numa apresentação do que o logo
   sozinho, e evita o mal-entendido de parecer que há framework aqui.
   -------------------------------------------------------------------------- */
const STACK = [
    { tec: 'python', nome: 'Python 3.13', papel: 'API e cálculo', nota: 'biblioteca padrão — sem Flask, sem FastAPI, sem pip no Pod' },
    { tec: 'javascript', nome: 'JavaScript', papel: 'painel (SPA)', nota: 'puro — sem React, sem build, sem bundler' },
    { tec: 'html5', nome: 'HTML5', papel: 'estrutura', nota: 'semântico e acessível por teclado' },
    { tec: 'css3', nome: 'CSS', papel: 'identidade', nota: 'variáveis de marca do Backstage, sem Tailwind' },
    { tec: 'openapiinitiative', nome: 'OpenAPI 3.1', papel: 'contrato', nota: 'spec escrita à mão antes do código (API first)' },
    { tec: 'amazonaws', nome: 'AWS Price List', papel: 'fonte dos preços', nota: 'bulk público, sem credencial — 288 MB no EC2' },
    { tec: 'kubernetes', nome: 'Kubernetes', papel: 'onde roda', nota: 'MicroK8s single-node on-premise' },
    { tec: 'argo', nome: 'Argo CD', papel: 'entrega GitOps', nota: 'sync automático com prune + selfHeal' },
    { tec: 'helm', nome: 'Helm', papel: 'empacotamento', nota: 'chart local no repositório, sem repo externo' },
    { tec: 'nginx', nome: 'NGINX Ingress', papel: 'exposição', nota: 'TLS pelo cert-manager, self-signed interno' },
    { tec: 'docker', nome: 'OCI', papel: 'runtime', nota: 'imagem OFICIAL python:3.13-alpine — sem Dockerfile' },
    { tec: 'pytest', nome: 'pytest', papel: 'testes', nota: 'única dependência de teste; a app não tem nenhuma' },
    { tec: 'git', nome: 'Git', papel: 'fonte da verdade', nota: 'git push é o deploy; nada de botão na console' }
];

const ROTULO_GRUPO = {
    computacao: 'Computação',
    armazenamento: 'Armazenamento',
    rede: 'Rede',
    operacao: 'Operação',
    outros: 'Outros'
};

/* ------------------------------------------------------------ formatação */
const escapar = (texto) =>
    String(texto).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const moeda = (valor, casas = 2) =>
    'US$ ' + valor.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

const numero = (valor, casas = 0) =>
    valor.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

const semZeros = (valor) => {
    if (Number.isInteger(valor)) return numero(valor);
    return numero(valor, valor < 1 ? 4 : 2);
};

/* --------------------------------------------------------------- avisos */
function mostrarAviso(texto, tipo) {
    const alvo = document.getElementById('aviso');
    alvo.className = 'aviso' + (tipo === 'erro' ? '' : '');
    alvo.innerHTML = texto;
    alvo.classList.remove('escondido');
}

function esconderAviso() {
    document.getElementById('aviso').classList.add('escondido');
}

/* ---------------------------------------------------------------- carga */
async function carregar(recarregando) {
    try {
        const sufixo = recarregando ? `&t=${Date.now()}` : '';
        const resposta = await fetch(`/api/calcular?horas=${estado.horas}${sufixo}`, { cache: 'no-store' });
        if (!resposta.ok) {
            const corpo = await resposta.json().catch(() => ({}));
            throw new Error(corpo.erro || `HTTP ${resposta.status}`);
        }
        estado.dados = await resposta.json();
        esconderAviso();
        render();
    } catch (erro) {
        mostrarAviso(
            `<strong>A API não respondeu.</strong> ${escapar(erro.message)}<br>` +
            'A página e a API sobem no mesmo Pod: se o Pod acabou de iniciar, aguarde alguns segundos e use <em>Recarregar preços</em>.',
            'erro'
        );
    }
}

/* -------------------------------------------------------------- desenho */
function render() {
    const d = estado.dados;
    if (!d) return;
    renderFonte(d);
    renderKpis(d);
    renderBarras(d);
    renderTabela(d);
    renderLacunas(d);
    renderPremissas(d);
    renderProcedencia(d);
    document.getElementById('dica-janela').textContent =
        `${numero(d.horas)} h equivalem a ${numero(d.horas / 24, 1)} dias. ` +
        `Projeção de um mês (730 h): ${moeda(d.mes.total)}.`;
}

function renderFonte(d) {
    const gerado = new Date(d.gerado_em);
    const dias = Math.floor((Date.now() - gerado.getTime()) / 86400000);
    const selo = document.getElementById('selo-fonte');

    if (dias <= 30) {
        selo.className = 'selo';
        selo.textContent = dias === 0 ? 'preços de hoje' : `preços de ${dias} dia(s)`;
    } else {
        selo.className = 'selo velho';
        selo.textContent = `snapshot com ${dias} dias — atualizar`;
    }

    const servicos = d.procedencia?.servicos || {};
    const partes = Object.entries(servicos).map(([nome, info]) => `${nome} ${String(info.publicationDate || '?').slice(0, 10)}`);
    document.getElementById('fonte-detalhe').textContent = partes.length ? `publicationDate: ${partes.join(' · ')}` : '';
    document.getElementById('snapshot-info').textContent =
        `Snapshot gerado em ${gerado.toLocaleString('pt-BR')} a partir da lista oficial da AWS.`;
}

function renderKpis(d) {
    const kpis = [
        { rotulo: `Total em ${numero(d.horas)} h`, valor: moeda(d.total), detalhe: `${numero(d.horas / 24, 1)} dias · ${d.itens.length} linhas`, destaque: true },
        { rotulo: 'Por dia', valor: moeda(d.total_por_dia), detalhe: `por hora: ${moeda(d.total_por_hora, 4)}` },
        { rotulo: 'Projeção 1 mês (730 h)', valor: moeda(d.mes.total), detalhe: `≈ ${numero(d.mes.total / (d.total || 1), 1)}x a janela atual` },
        { rotulo: 'Maior linha', valor: moeda(d.itens[0]?.subtotal || 0), detalhe: escapar((d.itens[0]?.descricao || '').slice(0, 48)) }
    ];
    document.getElementById('kpis').innerHTML = kpis
        .map(
            (k) => `<div class="kpi${k.destaque ? ' destaque' : ''}">
        <div class="kpi-rotulo">${k.rotulo}</div>
        <div class="kpi-valor">${k.valor}</div>
        <div class="kpi-detalhe">${k.detalhe}</div>
      </div>`
        )
        .join('');
}

function renderBarras(d) {
    const grupos = Object.entries(d.por_grupo);
    const maior = Math.max(...grupos.map(([, v]) => v), 0.0001);
    document.getElementById('barras-grupo').innerHTML = grupos
        .map(([grupo, valor]) => {
            const fatia = d.total ? (100 * valor) / d.total : 0;
            return `<div class="barra-linha">
        <div class="barra-nome">${escapar(ROTULO_GRUPO[grupo] || grupo)}</div>
        <div class="barra-trilho"><div class="barra-preenchida" style="width:${((100 * valor) / maior).toFixed(1)}%"></div></div>
        <div class="barra-valor">${moeda(valor)}<small>${numero(fatia, 1)}% do total</small></div>
      </div>`;
        })
        .join('');
}

function renderTabela(d) {
    const corpo = document.getElementById('corpo-tabela');
    let html = '';
    let grupoAtual = null;

    for (const item of d.itens) {
        if (item.grupo !== grupoAtual) {
            grupoAtual = item.grupo;
            html += `<tr class="grupo"><td colspan="6">${escapar(ROTULO_GRUPO[grupoAtual] || grupoAtual)}</td></tr>`;
        }
        const aberto = estado.expandidos.has(item.id);
        const quantidade = item.sem_preco ? item.quantidade : item.quantidade_efetiva;
        const unidade = item.sem_preco ? item.unidade_conta : item.unidade_oficial;
        const preco = item.sem_preco ? '<span class="sem-preco">—</span>' : moeda(item.preco_unitario, 6).replace(/0+$/, '').replace(/[,.]$/, '');
        const subtotal = item.sem_preco ? '<span class="sem-preco">não precificado</span>' : moeda(item.subtotal);
        const fatia = item.sem_preco || !d.total ? '—' : numero((100 * item.subtotal) / d.total, 1) + '%';

        html += `<tr class="item${aberto ? ' aberto' : ''}" data-id="${escapar(item.id)}" tabindex="0" role="button" aria-expanded="${aberto}">
      <td><span class="marcador">${aberto ? '▾' : '▸'}</span>${escapar(item.descricao)}</td>
      <td class="num">${semZeros(quantidade)}</td>
      <td>${escapar(unidade)}</td>
      <td class="num">${preco}</td>
      <td class="num">${subtotal}</td>
      <td class="num">${fatia}</td>
    </tr>`;

        if (aberto) {
            const detalhe = item.sem_preco
                ? `<strong>Por que não aparece valor:</strong> ${escapar(item.motivo)}`
                : `<strong>Por que existe:</strong> ${escapar(item.por_que)}<br>
           <strong>De onde vem o preço:</strong> <code>${escapar(item.tipo_uso)}</code> ·
           SKU <code>${escapar(item.sku)}</code> · ${escapar(item.preco_descricao)}`;
            html += `<tr class="motivo"><td colspan="6">${detalhe}</td></tr>`;
        }
    }

    corpo.innerHTML = html;
    document.getElementById('rodape-tabela').innerHTML = `<tr>
    <td colspan="4">Total na janela de ${numero(d.horas)} h</td>
    <td class="num">${moeda(d.total)}</td>
    <td class="num">100%</td>
  </tr>`;

    corpo.querySelectorAll('tr.item').forEach((linha) => {
        const alternar = () => {
            const id = linha.dataset.id;
            if (estado.expandidos.has(id)) estado.expandidos.delete(id);
            else estado.expandidos.add(id);
            renderTabela(estado.dados);
        };
        linha.addEventListener('click', alternar);
        linha.addEventListener('keydown', (evento) => {
            if (evento.key === 'Enter' || evento.key === ' ') {
                evento.preventDefault();
                alternar();
            }
        });
    });
}

function renderLacunas(d) {
    const alvo = document.getElementById('lacunas');
    if (!d.lacunas?.length) {
        alvo.innerHTML = '<div class="lacuna ok"><strong>Nenhuma lacuna declarada</strong>Todas as linhas do BOM têm preço no snapshot.</div>';
        return;
    }
    alvo.innerHTML = d.lacunas
        .map(
            (l) => `<div class="lacuna"><strong>${escapar(l.id)}</strong>
        ${escapar(l.descricao)}<br><em>${escapar(l.motivo)}</em></div>`
        )
        .join('');
}

function renderPremissas(d) {
    document.getElementById('premissas').innerHTML = (d.premissas || [])
        .map((p) => `<li>${escapar(p)}</li>`)
        .join('');
}

function renderProcedencia(d) {
    const servicos = d.procedencia?.servicos || {};
    const linhas = Object.entries(servicos)
        .map(
            ([nome, info]) => `<div class="proc-servico">
        <span>${escapar(nome)}</span>
        <span>publicationDate <strong>${escapar(info.publicationDate || '?')}</strong> ·
          versão ${escapar(info.version || '?')} ·
          ${numero(info.linhas_varridas || 0)} linhas varridas<br>${escapar(info.url_csv || '')}</span>
      </div>`
        )
        .join('');
    document.getElementById('procedencia').innerHTML =
        linhas + `<div class="proc-servico"><span>Snapshot</span><span>gerado em ${escapar(d.gerado_em)} · região ${escapar(d.bom?.regiao || '?')}</span></div>`;
}

/* ------------------------------------------------------------- eventos */
function ligarControles() {
    const campo = document.getElementById('horas');

    campo.addEventListener('input', () => {
        const valor = Number(campo.value);
        if (valor >= 1 && valor <= 8760) {
            estado.horas = valor;
            marcarAtalho(null);
            carregar();
        }
    });

    document.querySelectorAll('.atalhos button').forEach((botao) => {
        botao.addEventListener('click', () => {
            const valor = Number(botao.dataset.horas);
            campo.value = valor;
            estado.horas = valor;
            marcarAtalho(valor);
            carregar();
        });
    });

    document.getElementById('recarregar').addEventListener('click', () => carregar(true));

  document.getElementById('modelo').addEventListener('change', (evento) => aplicarModelo(evento.target.value.trim()));

  document.getElementById('regiao').addEventListener('change', (evento) => {
    const coletada = estado.descoberta?.regioes?.coletada;
    if (evento.target.value && evento.target.value !== coletada) {
      mostrarAviso(
        `Esta tela tem preços coletados para <strong>${escapar(coletada)}</strong>. ` +
        `Para precificar <strong>${escapar(evento.target.value)}</strong> é preciso coletar: ` +
        `<code>make snapshot --regiao ${escapar(evento.target.value)}</code> — ` +
        `enquanto isso, o número mostrado continua sendo o de ${escapar(coletada)}.`
      );
    } else {
      esconderAviso();
    }
  });

  document.getElementById('servico').addEventListener('change', (evento) => {
    const info = (estado.dados?.procedencia?.servicos || {})[evento.target.value];
    document.getElementById('dica-servico').textContent = info
      ? `${evento.target.value}: ${numero(info.linhas_varridas)} linhas varridas · publicationDate ${info.publicationDate}`
      : `${evento.target.value}: sem coleta nesta tela — o serviço existe na AWS, mas o preço dele não foi trazido para este snapshot.`;
  });
}

function marcarAtalho(valor) {
    document.querySelectorAll('.atalhos button').forEach((botao) => {
        botao.classList.toggle('ativo', Number(botao.dataset.horas) === valor);
    });
}

/* ---------------------------------------------------------------- stack */
function renderStack() {
  document.getElementById('stack').innerHTML = STACK.map((t) => `
    <div class="tec">
      <img src="tec-${escapar(t.tec)}.svg" alt="" loading="lazy">
      <div>
        <div class="tec-nome">${escapar(t.nome)}</div>
        <div class="tec-papel">${escapar(t.papel)}</div>
        <div class="tec-nota">${escapar(t.nota)}</div>
      </div>
    </div>`).join('');
}

/* ------------------------------------------------------------ descoberta */
/*
  Os três seletores NÃO têm lista no código: eles são preenchidos pelo que a
  fonte oficial responde. Região vem do region_index (106), serviço do índice
  raiz (271) e modelo do catálogo do arquivo da região (1.249 em us-east-1).

  A honestidade está no limite: só a região COLETADA tem preço. Escolher outra
  não recalcula nada — o aviso diz isso e diz o comando para coletar. Mostrar
  número de outra região seria inventar dado.
*/
async function carregarDescoberta() {
  try {
    const [regioes, servicos, catalogo] = await Promise.all([
      fetch('/api/regioes', { cache: 'no-store' }).then((r) => r.json()),
      fetch('/api/servicos', { cache: 'no-store' }).then((r) => r.json()),
      fetch('/api/catalogo?limite=1500', { cache: 'no-store' }).then((r) => r.json())
    ]);
    estado.descoberta = { regioes, servicos, catalogo };

    const selRegiao = document.getElementById('regiao');
    selRegiao.innerHTML = regioes.regioes
      .map((r) => `<option value="${escapar(r)}"${r === regioes.coletada ? ' selected' : ''}>${escapar(r)}${r === regioes.coletada ? ' — coletada' : ''}</option>`)
      .join('');
    document.getElementById('dica-regiao').textContent =
      `${regioes.total} regiões descobertas no region_index da AWS. Só a coletada tem catálogo e preço.`;

    const coletados = Object.keys(estado.dados?.procedencia?.servicos || {});
    const selServico = document.getElementById('servico');
    selServico.innerHTML = servicos.servicos
      .map((s) => `<option value="${escapar(s.codigo)}">${escapar(s.codigo)} — ${escapar(s.nome)}${s.codigo === 'AmazonEC2' ? ' · catálogo' : ''}</option>`)
      .join('');
    selServico.value = 'AmazonEC2';
    document.getElementById('dica-servico').textContent =
      `${servicos.total} serviços no índice raiz. ${coletados.length} com preço coletado: ${coletados.join(', ')}.`;

    document.getElementById('lista-modelos').innerHTML = catalogo.modelos
      .map((m) => `<option value="${escapar(m.tipo)}">${escapar(m.vcpu)} vCPU · ${escapar(m.memoria)} · ${escapar(m.familia)}</option>`)
      .join('');
    document.getElementById('total-modelos').textContent = `${catalogo.total_no_catalogo} modelos de ${catalogo.regiao}`;
    document.getElementById('dica-modelo').textContent =
      'Digite para filtrar entre todos os modelos da região. Nenhum está escrito no código: vieram do arquivo oficial.';
  } catch (erro) {
    document.getElementById('dica-modelo').textContent = `não foi possível carregar a descoberta: ${erro.message}`;
  }
}

function aplicarModelo(valor) {
  const modelos = estado.descoberta?.catalogo?.modelos || [];
  const dica = document.getElementById('dica-modelo');
  if (!valor) {
    estado.modelo = null;
    dica.textContent = 'Sem escolha: vale o modelo padrão declarado no BOM.';
    carregar();
    return;
  }
  const achado = modelos.find((m) => m.tipo === valor);
  if (!achado) {
    dica.textContent = `"${valor}" não está no catálogo desta região — o total NÃO foi alterado.`;
    return;
  }
  estado.modelo = valor;
  dica.textContent = `${achado.vcpu} vCPU · ${achado.memoria} · ${achado.familia} · US$ ${achado.preco}/h · SKU ${achado.sku}`;
  carregar();
}

renderStack();
ligarControles();
carregar().then(carregarDescoberta);
