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

/* ==========================================================================
   STACK DO LABORATÓRIO — o portfólio da ARQUITETURA, não só deste painel.

   Cada peça declara três coisas, e a terceira é a que interessa numa
   apresentação: o que ela PROPÕE dentro da arquitetura. Nome e logo sozinhos
   não explicam por que a peça está ali.

   O acervo do laboratório (Backstage/TechDocs) é linkado de dentro daqui: o
   painel aponta para a documentação, e a documentação descreve o painel.
   ========================================================================== */
const ACERVO = 'https://backstage.local/docs/default/component/documentacao-resilience/';
const linkAcervo = (caminho) => `${ACERVO}${caminho}/`;

const STACK = [
  {
    grupo: 'Plataforma — onde tudo roda',
    nota: 'Um node on-premise, com os addons que o MicroK8s já traz.',
    itens: [
      {
        tec: 'kubernetes',
        nome: 'MicroK8s',
        versao: '1.35.6',
        papel: 'O cluster single-node do laboratório',
        proposta: 'Escolhido pelos addons prontos (DNS, storage, registry): num node só, remontar cada peça à mão seria estudo repetido, não estudo novo.',
        doc: 'https://microk8s.io/docs'
      },
      {
        tec: 'helm',
        nome: 'Helm',
        versao: '3.19.0',
        papel: 'Empacota e parametriza tudo o que sobe',
        proposta: 'É o formato de entrega: cada componente é um chart com values versionados, e quem renderiza é o ArgoCD. Nada de manifesto solto com valores espalhados.',
        doc: 'https://helm.sh/docs/'
      },
      {
        tec: 'nginx',
        nome: 'NGINX Ingress',
        versao: 'chart 4.15.1',
        papel: 'A porta de entrada única do cluster',
        proposta: 'Decide qual serviço atende cada nome — argocd.local, backstage.local, calculadora.local. É ele que faz "um IP, vários apps".',
        doc: 'https://kubernetes.github.io/ingress-nginx/'
      },
      {
        tec: null,
        mono: 'LB',
        nome: 'MetalLB',
        versao: '0.16.1',
        papel: 'Dá IP real da LAN aos serviços LoadBalancer',
        proposta: 'Sem ele, nenhum *.local existiria: o endereço seria NodePort. Em modo L2 com a interface FIXADA (enp3s0), para não responder ARP na rede errada — está no troubleshooting do lab.',
        doc: 'https://metallb.universe.tf/'
      }
    ]
  },
  {
    grupo: 'Entrega — como o código chega no cluster',
    itens: [
      {
        tec: 'argo',
        nome: 'Argo CD',
        versao: 'app 3.5.2',
        papel: 'Reconcilia o cluster com o Git',
        proposta: 'git push É o deploy: auto-sync com prune e selfHeal. Este painel foi entregue por ele, sem nenhum apply manual na aplicação.',
        doc: 'https://argo-cd.readthedocs.io/'
      },
      {
        tec: 'git',
        nome: 'Git / GitHub',
        versao: 'fonte da verdade',
        papel: 'Onde vive a intenção do ambiente',
        proposta: 'Nada existe no cluster que não exista no histórico — e a branch diz quais arquivos cada assunto tocou. É o artefato de auditoria.',
        doc: 'https://git-scm.com/doc'
      },
      {
        tec: 'terraform',
        nome: 'Terraform',
        versao: '1.11.3 · AWS 5.100',
        papel: 'O que é da AWS e precisa ser declarado',
        proposta: 'Buckets, IAM e SSO nascem daqui. O mesmo stack aponta para o emulador ou para a conta real sem trocar uma linha de código — só variável de ambiente.',
        doc: 'https://developer.hashicorp.com/terraform/docs'
      }
    ]
  },
  {
    grupo: 'Malha de serviço',
    itens: [
      {
        tec: 'istio',
        nome: 'Istio',
        versao: '1.30.4',
        papel: 'mTLS, roteamento e telemetria sem tocar no código',
        proposta: 'Aqui ele sustenta o Bookinfo como bancada de estudo de tráfego e de injeção de sidecar. IMPORTANTE: ESTE painel não está na malha — escolha declarada, para uma tela interna não pagar o custo de um sidecar.',
        doc: 'https://istio.io/latest/docs/'
      }
    ]
  },
  {
    grupo: 'Observabilidade — o laboratório que se observa',
    itens: [
      {
        tec: 'prometheus',
        nome: 'Prometheus',
        versao: 'chart 91.2.1',
        papel: 'Coleta e armazena as métricas',
        proposta: 'A base de qualquer decisão de capacidade: sem série histórica, dimensionar vira chute com nome bonito.',
        doc: 'https://prometheus.io/docs/'
      },
      {
        tec: 'grafana',
        nome: 'Grafana',
        versao: 'chart 91.2.1',
        papel: 'Lê o Prometheus e mostra',
        proposta: 'Onde o número vira conversa. O banco dele já está no alvo da regra de ouro do lab: uma instância PostgreSQL compartilhada.',
        doc: 'https://grafana.com/docs/'
      },
      {
        tec: null,
        mono: 'K',
        nome: 'Kiali',
        versao: 'op. 2.31.0',
        papel: 'A topologia e a saúde da malha',
        proposta: 'Responde "quem fala com quem" sem ler YAML — é o mapa do Istio, e o lugar onde uma quebra de mTLS aparece primeiro.',
        doc: 'https://kiali.io/docs/'
      },
      {
        tec: null,
        mono: 'J',
        nome: 'Jaeger',
        versao: 'op. 2.57.0',
        papel: 'Traço distribuído',
        proposta: 'Segue a requisição por dentro dos serviços: é o que separa "está lento" de "está lento AQUI".',
        doc: 'https://www.jaegertracing.io/docs/'
      },
      {
        tec: null,
        mono: 'MS',
        nome: 'metrics-server',
        versao: 'chart 3.14.0',
        papel: 'Métricas de CPU e memória para o HPA',
        proposta: 'Sem ele o HPA não consegue decidir escala — e foi por isso que Istio e gateway apareciam como Degraded no ArgoCD, o que está registrado no troubleshooting.',
        doc: 'https://github.com/kubernetes-sigs/metrics-server'
      }
    ]
  },
  {
    grupo: 'Identidade e dados',
    itens: [
      {
        tec: 'keycloak',
        nome: 'Keycloak',
        versao: '26.0.7',
        papel: 'O provedor de identidade',
        proposta: 'O login do Backstage é OIDC contra ele. Usuários, roles e client saem de um provisioner idempotente — não de cliques no console, que ninguém reproduz.',
        doc: 'https://www.keycloak.org/documentation'
      },
      {
        tec: 'postgresql',
        nome: 'PostgreSQL',
        versao: '17-alpine',
        papel: 'A instância única compartilhada',
        proposta: 'Regra de ouro do laboratório: UM PostgreSQL, com database e user por aplicação. Nada de um banco por app — o custo de operar isso não paga.',
        doc: 'https://www.postgresql.org/docs/'
      }
    ]
  },
  {
    grupo: 'Portal e documentação',
    itens: [
      {
        tec: 'backstage',
        nome: 'Backstage',
        versao: '1.54.0',
        papel: 'O portal do desenvolvedor',
        proposta: 'Catálogo, templates e o acervo. E é DELE que este painel herdou a identidade visual: os mesmos tokens de cor, sem paleta paralela.',
        doc: 'https://backstage.io/docs/'
      },
      {
        tec: null,
        mono: 'TD',
        nome: 'TechDocs',
        versao: 'mkdocs 1.6.1',
        papel: 'O acervo publicado',
        proposta: 'O mkdocs roda DENTRO do cluster, em CronJob com imagens oficiais, e publica o site no bucket. A documentação viaja como artefato de deploy, não como anexo.',
        doc: linkAcervo('praticas')
      }
    ]
  },
  {
    grupo: 'Certificados',
    itens: [
      {
        tec: null,
        mono: 'CM',
        nome: 'cert-manager',
        versao: 'chart 1.21.2',
        papel: 'Emite e renova o TLS de cada host',
        proposta: 'Sem ele, cada aplicação exigiria certificado na mão e alguém lembrando do vencimento. Hoje cada host tem o seu, emitido por um ClusterIssuer self-signed interno.',
        doc: 'https://cert-manager.io/docs/'
      },
      {
        tec: null,
        mono: 'TM',
        nome: 'trust-manager',
        versao: '0.25.0',
        papel: 'Distribui a CA interna para os namespaces',
        proposta: 'É o que faz o processo Node do Backstage confiar no certificado interno do Keycloak. O trust anchor das conversas entre serviços — e como ele foi validado está no acervo.',
        doc: linkAcervo('certificados/01-trust-anchor-interno')
      }
    ]
  },
  {
    grupo: 'AWS — onde o custo nasce',
    itens: [
      {
        tec: 'amazonaws',
        nome: 'AWS Price List',
        versao: 'bulk oficial',
        papel: 'A fonte dos preços deste painel',
        proposta: 'Pública e sem credencial: NENHUM valor aqui foi digitado à mão, e o snapshot carrega a publicationDate que a própria AWS publica. Um preço digitado envelhece sem avisar; um preço com data, não.',
        doc: 'https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_Operations_AWS_Price_List.html'
      },
      {
        tec: null,
        mono: 'FL',
        nome: 'Floci',
        versao: '2.1.0',
        papel: 'Emulador de AWS no laboratório',
        proposta: 'Permite o Terraform rodar em casa, sem conta real: S3, IAM e Lambda respondem local. Ao migrar para a AWS de verdade ele desaparece da topologia — e com ele os skip_* do provider.',
        doc: linkAcervo('aws')
      }
    ]
  },
  {
    grupo: 'Este painel',
    itens: [
      {
        tec: 'python',
        nome: 'Python',
        versao: '3.13',
        papel: 'A API e o cálculo',
        proposta: 'Biblioteca padrão apenas: sem Flask, sem FastAPI, sem pip dentro do Pod. É isso que permite a imagem ser a OFICIAL e o app rodar de dentro de ConfigMap.',
        doc: 'https://docs.python.org/3/'
      },
      {
        tec: 'javascript',
        nome: 'JavaScript',
        versao: 'ES2020',
        papel: 'Este painel (SPA)',
        proposta: 'Puro: sem React, sem build, sem bundler e sem CDN em runtime. Ler o repositório e ler o que roda é a mesma coisa — de propósito.',
        doc: 'https://developer.mozilla.org/pt-BR/docs/Web/JavaScript'
      },
      {
        tec: 'html5',
        nome: 'HTML5 + CSS',
        versao: 'sem framework',
        papel: 'Estrutura e identidade visual',
        proposta: 'Semântico e navegável por teclado. As cores são as MESMAS variáveis do tema do Backstage — trocar a marca continua sendo trocar num lugar só.',
        doc: 'https://developer.mozilla.org/pt-BR/docs/Web/HTML'
      },
      {
        tec: 'openapiinitiative',
        nome: 'OpenAPI 3.1',
        versao: 'spec 1.0.0',
        papel: 'O contrato da API',
        proposta: 'Escrita à mão ANTES do código (API first): é o artefato de desenho, e a tela /api/docs é ela renderizada. Importável em Swagger, Postman e gerador de cliente.',
        doc: 'https://spec.openapis.org/oas/v3.1.0'
      },
      {
        tec: 'docker',
        nome: 'OCI',
        versao: 'python:3.13-alpine',
        papel: 'O runtime',
        proposta: 'Imagem oficial com tag fixa: não existe Dockerfile próprio, nem registry para manter, nem tag para esquecer de subir.',
        doc: 'https://hub.docker.com/_/python'
      },
      {
        tec: 'pytest',
        nome: 'pytest',
        versao: '87 testes',
        papel: 'A verificação',
        proposta: 'A única dependência de teste — a aplicação não tem nenhuma. Na primeira execução ela reprovou três bugs reais, um deles uma conta 4x errada.',
        doc: 'https://docs.pytest.org/'
      }
    ]
  }
];

/* --------------------------------------------------------------------------
   NO RADAR — o que ainda NÃO existe, declarado para não virar folclore.

   Fica na página de propósito: portfólio que só mostra o pronto esconde a
   direção. E apresentar o que vem depois é parte de mostrar o trabalho.
   -------------------------------------------------------------------------- */
const RADAR = [
  { nome: 'GitHub Actions', o_que: 'CI para validar código e imagem a cada push, antes de qualquer coisa chegar ao cluster.' },
  { nome: 'Bibliotecas homologadas', o_que: 'A lista do que PODE e do que NÃO PODE entrar como dependência, com o critério escrito — em vez de decisão por gosto.' },
  { nome: 'Bootstrap do host', o_que: 'Subir o node do zero de forma declarada. Hoje isso está documentado e NÃO declarado, e esse é o furo de replicabilidade que a gente já nomeou.' },
  { nome: 'EKS', o_que: 'A evolução do single-node para o Kubernetes gerenciado, em outro momento.' },
  { nome: 'Desenho de arquitetura', o_que: 'Diagramas com draw.io para acompanhar esta página na apresentação.' }
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
function cartaoTec(t) {
  // Kiali, Jaeger, cert-manager e trust-manager não têm marca publicada no
  // Simple Icons. Monograma resolve melhor que um buraco na grade — e melhor
  // que um logo inventado, que seria mentira visual.
  const marca = t.tec
    ? `<img src="tec-${escapar(t.tec)}.svg" alt="" loading="lazy">`
    : `<span class="tec-mono" aria-hidden="true">${escapar(t.mono || '?')}</span>`;
  return `
    <article class="tec">
      <div class="tec-cabecalho">
        ${marca}
        <div>
          <div class="tec-nome">${escapar(t.nome)}</div>
          <div class="tec-versao">${escapar(t.versao)}</div>
        </div>
      </div>
      <div class="tec-papel">${escapar(t.papel)}</div>
      <p class="tec-proposta">${escapar(t.proposta)}</p>
      <a class="tec-doc" href="${escapar(t.doc)}" target="_blank" rel="noopener">documentação ↗</a>
    </article>`;
}

function renderStack() {
  document.getElementById('stack').innerHTML = STACK.map((bloco) => `
    <section class="stack-grupo">
      <h3>${escapar(bloco.grupo)}</h3>
      ${bloco.nota ? `<p class="stack-nota">${escapar(bloco.nota)}</p>` : ''}
      <div class="stack-grade">${bloco.itens.map(cartaoTec).join('')}</div>
    </section>`).join('');
}

function renderRadar() {
  document.getElementById('radar').innerHTML = RADAR.map((r) => `
    <div class="radar-item">
      <span class="radar-nome">${escapar(r.nome)}</span>
      <span class="radar-que">${escapar(r.o_que)}</span>
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
renderRadar();
ligarControles();
carregar().then(carregarDescoberta);
