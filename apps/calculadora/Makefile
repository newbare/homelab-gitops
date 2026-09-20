# ==========================================================================
# Calculadora Resilience — alvos do dia a dia
#
# Espelha o padrão de infrastructure/keycloak/scripts/Makefile: o que se digita
# todo dia fica aqui, e o `make` sozinho explica.
#
# A APLICAÇÃO NÃO TEM DEPENDÊNCIA — roda com a biblioteca padrão do Python.
# O `.venv` existe só para o pytest.
# ==========================================================================

PY ?= python3
VENV := .venv
PY_VENV := $(VENV)/bin/python

.DEFAULT_GOAL := ajuda
.PHONY: ajuda venv teste teste-precos teste-snapshot teste-servidor teste-pg teste-carga \
        snapshot tabela servir limpar \
        f2 banco-bg banco-parar banco-forward banco-criar schema carga carga-seca carga-conferir

# ---------------------------------------------------------------------------
# F2 — a carga dos precos no PostgreSQL
#
# O PostgreSQL do laboratorio vive DENTRO do cluster, e a instancia nao e
# exposta: o caminho e o port-forward. Por isso os alvos abaixo sobem o
# encaminhamento antes e derrubam depois — em vez de exigir que alguem deixe
# uma aba aberta sem esquecer de fechar.
# ---------------------------------------------------------------------------
PG_NS    ?= postgresql
PG_POD   ?= postgresql-0
PG_SVC   ?= postgresql
PG_LOCAL ?= 5432

CALC_BANCO ?= calculadora
CALC_USER  ?= calculadora
CALC_SENHA ?= calculadora-password

# As credenciais vao por AMBIENTE, nunca por argumento de linha de comando:
# argumento aparece no `ps` de qualquer processo da maquina.
PG_ENV := PGHOST=127.0.0.1 PGPORT=$(PG_LOCAL) PGUSER=$(CALC_USER) \
          PGPASSWORD=$(CALC_SENHA) PGDATABASE=$(CALC_BANCO)
PG_PID := /tmp/calculadora-pg-forward.pid
PG_LOG := /tmp/calculadora-pg-forward.log

ajuda:
	@echo "Calculadora Resilience — o que dá para fazer aqui"
	@echo ""
	@echo "  make venv            cria o .venv e instala o pytest (só para teste)"
	@echo "  make teste           roda a suíte inteira"
	@echo "  make teste-precos    só a aritmética (rápido, não depende de rede)"
	@echo "  make teste-snapshot  só o contrato do dado coletado"
	@echo "  make teste-servidor  só a borda HTTP"
	@echo "  make snapshot        RECOLETA os precos da lista oficial (EC2 ~288 MB)"
	@echo "  make tabela          custo da janela de 7 dias, no terminal"
	@echo "  make servir          sobe o painel local em http://localhost:8080"
	@echo ""
	@echo "  F2 — precos no PostgreSQL (o motor agnostico):"
	@echo "  make f2              faz TUDO: banco, schema, carga e conferencia"
	@echo "  make banco-bg        so o encaminhamento de porta (fica aberto)"
	@echo "  make banco-criar     cria o banco e o usuario calculadora (idempotente)"
	@echo "  make schema          aplica sql/001-schema.sql (idempotente)"
	@echo "  make carga-seca      coleta e confere SEM gravar nada"
	@echo "  make carga           carrega os precos (grava)"
	@echo "  make carga-conferir  mostra o que esta na base e o historico de cargas"
	@echo "  make banco-parar     derruba o encaminhamento de porta"
	@echo ""
	@echo "  make limpar          remove .venv e __pycache__"
	@echo ""
	@echo "Teste: $(PY_VENV) -m pytest tests/ -v"

venv: $(PY_VENV)

$(PY_VENV):
	$(PY) -m venv $(VENV)
	$(PY_VENV) -m pip install --quiet --upgrade pip
	$(PY_VENV) -m pip install --quiet -r requirements-dev.txt
	@echo "ambiente pronto em $(VENV)"

teste: venv
	$(PY_VENV) -m pytest tests/ -v

teste-precos: venv
	$(PY_VENV) -m pytest tests/test_precos.py -v

teste-snapshot: venv
	$(PY_VENV) -m pytest tests/test_snapshot.py -v

teste-servidor: venv
	$(PY_VENV) -m pytest tests/test_servidor.py -v

teste-pg: venv
	$(PY_VENV) -m pytest tests/test_pg.py -v

teste-carga: venv
	$(PY_VENV) -m pytest tests/test_carga.py -v

# Passa --dump sempre: sem o dump, um filtro frouxo custa outra passada de
# 288 MB para ser diagnosticado.
snapshot:
	$(PY) buscar_precos.py --dump /tmp/calculadora-candidatos.json

tabela:
	$(PY) calcular.py

servir:
	$(PY) api/servidor.py --web web --dados dados --endereco 127.0.0.1 --porta 8080

# ---------------------------------------------------------------------------
# F2
# ---------------------------------------------------------------------------
# O fluxo completo com um comando. A ordem importa: o port-forward precisa
# estar de pe ANTES do schema (que fala com o banco) e o banco precisa existir
# antes do schema.
#
f2: banco-bg banco-criar schema carga carga-conferir banco-parar
	@echo ""
	@echo "F2 concluido."

banco-bg:
	@if [ -f $(PG_PID) ] && kill -0 $$(cat $(PG_PID)) 2>/dev/null; then \
		echo "encaminhamento de porta ja ativo (pid $$(cat $(PG_PID)))"; \
	else \
		kubectl -n $(PG_NS) port-forward svc/$(PG_SVC) $(PG_LOCAL):5432 > $(PG_LOG) 2>&1 & \
		echo $$! > $(PG_PID); \
		sleep 2; \
		echo "encaminhamento de porta ativo em 127.0.0.1:$(PG_LOCAL) (pid $$(cat $(PG_PID)))"; \
	fi

# Em primeiro plano, para quem prefere ver o trafego numa aba propria.
banco-forward:
	kubectl -n $(PG_NS) port-forward svc/$(PG_SVC) $(PG_LOCAL):5432

banco-parar:
	@if [ -f $(PG_PID) ] && kill -0 $$(cat $(PG_PID)) 2>/dev/null; then \
		kill $$(cat $(PG_PID)) && echo "encaminhamento de porta encerrado"; \
	else \
		echo "nenhum encaminhamento ativo"; \
	fi
	@rm -f $(PG_PID)

# Passo que exige SUPERUSUARIO: criar banco e usuario. Roda o psql DENTRO do
# pod, com a senha que ja esta no ambiente dele — nenhuma senha de superusuario
# passa por esta maquina nem entra no historico do shell.
banco-criar:
	@kubectl -n $(PG_NS) exec -i $(PG_POD) -- sh -c 'PGPASSWORD="$$POSTGRES_PASSWORD" psql -U postgres -d postgres' < sql/000-banco.sql
	@echo "banco $(CALC_BANCO) e usuario $(CALC_USER) prontos"

# O schema e aplicado PELO PYTHON, e nao por um psql instalado aqui: e o mesmo
# caminho que a aplicacao usa, entao o que passa no teste e o que roda no Pod.
schema:
	$(PG_ENV) $(PY) carregar_precos.py --aplicar-schema

# Confere tudo e NAO grava. Rode este antes do `carga` -- e o mesmo portao.
carga-seca:
	$(PG_ENV) $(PY) carregar_precos.py --dry-run --enriquecer

# A carga que grava. O portao recusa a carga inteira se a fonte se contradizer.
carga:
	$(PG_ENV) $(PY) carregar_precos.py --enriquecer

carga-conferir:
	$(PG_ENV) $(PY) carregar_precos.py --conferir-carga

limpar:
	rm -rf $(VENV)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "limpo"
