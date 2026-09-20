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
.PHONY: ajuda venv teste teste-precos teste-snapshot teste-servidor snapshot tabela servir limpar

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

# Passa --dump sempre: sem o dump, um filtro frouxo custa outra passada de
# 288 MB para ser diagnosticado.
snapshot:
	$(PY) buscar_precos.py --dump /tmp/calculadora-candidatos.json

tabela:
	$(PY) calcular.py

servir:
	$(PY) api/servidor.py --web web --dados dados --endereco 127.0.0.1 --porta 8080

limpar:
	rm -rf $(VENV)
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	@echo "limpo"
