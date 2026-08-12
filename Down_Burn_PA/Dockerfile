# =============================================================================
# ESTÁGIO BASE
# Imagem Python 3.13 slim (Debian Trixie) com GDAL instalado via repos Debian.
# A variante "slim" reduz o tamanho final; GDAL 3.x já está disponível
# nativamente no Trixie, sem necessidade de PPA ou compilação manual.
# =============================================================================
FROM python:3.13-slim AS base

# -----------------------------------------------------------------------------
# Variáveis de ambiente do build
#   DEBIAN_FRONTEND=noninteractive  → suprime prompts interativos do apt
#   PYTHONDONTWRITEBYTECODE=1       → não gera arquivos .pyc no container
#   PYTHONUNBUFFERED=1              → logs aparecem em tempo real no console
# -----------------------------------------------------------------------------
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONUNBUFFERED=1

# -----------------------------------------------------------------------------
# Dependências de sistema
# Instaladas em uma única camada RUN para minimizar o número de layers.
#   gdal-bin / libgdal-dev    → binários e headers do GDAL (raster/vetor)
#   libgeos-dev               → geometrias (Shapely, GeoPandas)
#   libproj-dev               → reprojeção de CRS (pyproj)
#   libspatialindex-dev       → índice espacial R-tree (usado pelo GeoPandas)
#   python3-dev / build-essential / pkg-config → compilação de extensões C
# O cache do apt é removido ao final para manter a imagem enxuta.
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        gdal-bin \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
        libspatialindex-dev \
        python3-dev \
        build-essential \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# DEPENDÊNCIAS PYTHON
# O GDAL Python deve ter versão idêntica ao GDAL do sistema; por isso a versão
# é detectada dinamicamente com gdal-config antes do pip install.
# =============================================================================
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && GDAL_VERSION=$(gdal-config --version) \
 && pip install --no-cache-dir "GDAL==${GDAL_VERSION}" \
 && pip install --no-cache-dir -r /tmp/requirements.txt

# =============================================================================
# SCRIPTS DA APLICAÇÃO
# O WORKDIR /app é criado automaticamente pelo Docker se não existir.
# Apenas a pasta scripts/ é copiada — dados e configs são montados em runtime
# via volumes definidos no docker-compose.yml.
# =============================================================================
WORKDIR /app
COPY scripts/ /app/scripts/
