"""
Script Refatorado e Corrigido — Download dos Dados MODIS MCD64A1 via GEE
"""

import os
import time
import json
import math
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import ee
import requests
import rasterio
import yaml
from rasterio.merge import merge

class GEEDownloader:
    def __init__(self, config_path: str = "config.yaml"):
        # 1. Carregamento de Configurações
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)["down"]
        
        self.cfg = cfg
        self.out_dir = Path(cfg["out_dir"])
        self.log_file = self.out_dir / cfg["log_file"]
        self.out_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Autenticação GEE
        print("Autenticando no GEE...")
        credentials = ee.ServiceAccountCredentials(cfg["service_account"], cfg["key_file"])
        ee.Initialize(credentials, project=cfg["project"])
        
        # 3. Definição da Região e Coleção
        self.region = (
            ee.FeatureCollection(cfg["area_asset"])
            .filter(ee.Filter.eq(cfg["area_attr"], cfg["area_name"]))
            .geometry()
        )
        self.collection_base = ee.ImageCollection(cfg["collection"]).select(cfg["selection"])
        self.log_data = self._load_log()

    # --- GERENCIAMENTO DE DISCO E LOG ---

    def _load_log(self) -> dict:
        return json.loads(self.log_file.read_text()) if self.log_file.exists() else {}

    def _save_log(self):
        self.log_file.write_text(json.dumps(self.log_data, indent=2))

    def _get_filepath(self, year: int, month: int) -> Path:
        return self.out_dir / str(year) / f"{self.cfg['nome_raster']}_{year}_{month:02d}.tif"

    def _is_valid_tif(self, filepath: Path) -> bool:
        return filepath.exists() and filepath.stat().st_size > 0

    def get_missing_months(self) -> list:
        missing = []
        y, m = self.cfg["start_year"], self.cfg["start_month"]
        end_y, end_m = self.cfg["end_year"], self.cfg["end_month"]
        
        while (y, m) <= (end_y, end_m):
            if not self._is_valid_tif(self._get_filepath(y, m)):
                missing.append((y, m))
            m = 1 if m == 12 else m + 1
            if m == 1: y += 1
            
        return missing

    # --- LÓGICA DE DOWNLOAD ---

    def _download_zip(self, url: str, filepath: Path):
        """Baixa e extrai o GeoTIFF de uma URL ZIP via HTTP Streaming."""
        zip_path = filepath.with_suffix(".zip")
        
        for attempt in range(1, self.cfg["max_retries"] + 1):
            try:
                with requests.get(url, stream=True, timeout=self.cfg["timeout_s"]) as r:
                    r.raise_for_status()
                    with open(zip_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=self.cfg["chunk_size"]):
                            if chunk: f.write(chunk)
                
                with zipfile.ZipFile(zip_path) as z:
                    tifs = [n for n in z.namelist() if n.endswith(".tif")]
                    if not tifs: raise RuntimeError("Nenhum .tif encontrado no zip.")
                    with z.open(tifs[0]) as src, open(filepath, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                
                zip_path.unlink()
                return
            except requests.exceptions.RequestException as e:
                if attempt == self.cfg["max_retries"]: raise RuntimeError(f"Falha após {attempt} tentativas: {e}")
                time.sleep(10 * attempt)

    def _download_tiled(self, image: ee.Image, filepath: Path, size_mb: float):
        """Divide a imagem em grid e une os tiles com rasterio."""
        n_tiles = math.ceil(size_mb / self.cfg["gee_limit_mb"])
        n_cols = math.ceil(math.sqrt(n_tiles))
        n_rows = math.ceil(n_tiles / n_cols)
        
        coords = self.region.bounds().getInfo()["coordinates"][0]
        minx, miny = min(c[0] for c in coords), min(c[1] for c in coords)
        dx = (max(c[0] for c in coords) - minx) / n_cols
        dy = (max(c[1] for c in coords) - miny) / n_rows

        tiles_dir = filepath.parent / f"_tiles_{filepath.stem}"
        tiles_dir.mkdir(parents=True, exist_ok=True)
        tile_files = []

        for row in range(n_rows):
            for col in range(n_cols):
                tile_path = tiles_dir / f"tile_{row:02d}_{col:02d}.tif"
                if not tile_path.exists():
                    bbox = ee.Geometry.BBox(minx + col * dx, miny + row * dy, 
                                            minx + (col + 1) * dx, miny + (row + 1) * dy)
                    url = image.getDownloadURL({
                        "name": tile_path.stem, "scale": self.cfg["scale"],
                        "region": bbox, "crs": self.cfg["crs"],
                        "filePerBand": False, "fileFormat": "ZIPPED_GEO_TIFF"
                    })
                    self._download_zip(url, tile_path)
                tile_files.append(tile_path)

        # Mesclar tiles
        datasets = [rasterio.open(str(f)) for f in tile_files]
        mosaic, transform = merge(datasets)
        profile = datasets[0].profile.copy()
        profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform, compress="lzw", tiled=True)
        
        with rasterio.open(str(filepath), "w", **profile) as dst:
            dst.write(mosaic)
            
        for ds in datasets: ds.close()
        shutil.rmtree(tiles_dir, ignore_errors=True)

    def process_month(self, year: int, month: int, filepath: Path) -> dict:
        """Processa um mês específico decidindo dinamicamente a estratégia baseada na resposta da API."""
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
        
        col = self.collection_base.filterDate(start_date, end_date)
        if col.size().getInfo() == 0:
            return {"status": "sem_dado", "ts": datetime.now().isoformat()}

        image = col.first().clip(self.region)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Tenta download direto. Se o tamanho da imagem for maior que o limite do GEE,
            # a API lança um erro imediatamente (sem fazer download) contendo o tamanho real.
            url = image.getDownloadURL({
                "name": filepath.stem, "scale": self.cfg["scale"],
                "region": self.region, "crs": self.cfg["crs"],
                "filePerBand": False, "fileFormat": "ZIPPED_GEO_TIFF"
            })
            self._download_zip(url, filepath)
        except Exception as e:
            # Captura a mensagem de limite de tamanho e extrai os bytes exatos
            match = re.search(r"Total request size \((\d+)", str(e))
            if match:
                real_size_mb = int(match.group(1)) / (1024 * 1024)
                self._download_tiled(image, filepath, real_size_mb)
            else:
                raise # Se for outro tipo de erro (ex: quota, credenciais, timeout), repassa

        if not self._is_valid_tif(filepath):
            if filepath.exists(): filepath.unlink()
            raise RuntimeError("Arquivo criado vazio (0 bytes)")

        return {"status": "ok", "ts": datetime.now().isoformat(), "size_kb": round(filepath.stat().st_size / 1024, 1)}

    # --- EXECUÇÃO PRINCIPAL ---
    
    def run(self):
        missing = self.get_missing_months()
        print(f"Auditoria: {len(missing)} meses faltando para download.")
        if not missing: return

        sucessos = 0
        erros = []

        for idx, (y, m) in enumerate(missing, 1):
            chave = f"{y}-{m:02d}"
            filepath = self._get_filepath(y, m)
            print(f"[{idx}/{len(missing)}] {chave} ...", end=" ", flush=True)

            try:
                res = self.process_month(y, m, filepath)
                self.log_data[chave] = res
                if res["status"] == "ok":
                    print(f"ok ({res.get('size_kb', 0):.0f} KB)")
                    sucessos += 1
                else:
                    print("sem dado no GEE — pulando")
                time.sleep(self.cfg["pause_sec"])
            except Exception as e:
                print(f"ERRO FINAL — {e}")
                self.log_data[chave] = {"status": "erro", "ts": datetime.now().isoformat(), "msg": str(e)}
                erros.append((y, m, str(e)))

            self._save_log()

        print("\n" + "=" * 55 + f"\n  Baixados: {sucessos} | Erros: {len(erros)}\n" + "=" * 55)

if __name__ == "__main__":
    GEEDownloader().run()