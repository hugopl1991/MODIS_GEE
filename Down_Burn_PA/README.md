# MODIS_GEE

Projeto para baixar e organizar produtos MODIS (Burn Date) e preparar insumos raster/vetoriais para análises.

## Descrição

Este repositório contém pipelines e utilitários para download e organização de dados MODIS Burn Date. Há versões/configurações separadas para diferentes áreas (por exemplo, Brasil e PA) e scripts úteis em `scripts/`.

## Estrutura do repositório

- `Down_Burn_BR/` — pipeline e recursos para Brasil.
- `Down_Burn_PA/` — pipeline e recursos para Áreas Protegidas (PA).
- `inputs/` — shapefiles e rasters necessários (ex.: `Shape_estados/`, `Raster/`).
- `scripts/` — scripts Python reutilizáveis (ex.: `NPI_Down_*.py`).
- `requirements.txt` — dependências Python.

## Pré-requisitos

- Python 3.8+ (para execução local dos scripts) e `pip`.
- Ou Docker + Docker Compose (para executar os serviços isoladamente).
- Conta/credenciais do Google Earth Engine (se os scripts utilizarem GEE). Coloque o JSON de conta de serviço na raiz do projeto e exporte a variável de ambiente `GOOGLE_APPLICATION_CREDENTIALS` apontando para ele.

## Instalação (local, com Python)

1. Crie e ative um ambiente virtual (recomendado).

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / macOS
.venv\Scripts\activate    # Windows
```

2. Instale dependências:

```bash
pip install -r requirements.txt
```

## Executando (exemplos)

- Usando Docker (ex.: pipeline BR):

```bash
cd Down_Burn_BR
docker-compose up --build
```

- Executando script Python localmente (verifique `config.yaml` antes):

```bash
python scripts/NPI_Down_v4.py
```

Observação: Alguns pipelines dependem de parâmetros em `config.yaml` dentro de cada pasta (`Down_Burn_BR/config.yaml` etc.). Edite-os conforme necessário antes da execução.

## Inputs e dados

- Os shapefiles por estado estão em `inputs/Shape_estados/`.
- Os rasters brutos de Burn Date ficam em `inputs/Raster/MODIS_BurnDate_RAW/` organizados por ano.

## Contribuindo

Abra um issue descrevendo a sugestão ou correção desejada. Para mudanças de código, envie um pull request com descrição clara das alterações.

## Contato

Para dúvidas, abra uma issue ou contate o mantenedor do projeto.

