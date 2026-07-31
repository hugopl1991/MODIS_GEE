"""
Script Refatorado — Download dos Dados MODIS MCD64A1 via GEE (Limite Estadual)
"""

import json
import time
from datetime import datetime
from pathlib import Path

import ee
import geemap
import yaml

class GEEDownloaderEstadual:
    def __init__(self, config_path: str = "config.yaml"):
        # 1. Carregamento de Configurações
        with open(config_path, "r", encoding="utf-8") as f:
            full_config = yaml.safe_load(f)
            
        self.cfg = full_config["down"]
        self.shp_path = Path(full_config["global"]["shp_path"])
        
        self.out_dir = Path(self.cfg["out_dir"])
        self.log_file = self.out_dir / self.cfg["log_file"]
        self.out_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Autenticação GEE
        print("Autenticando e carregando shapefile no GEE...")
        credentials = ee.ServiceAccountCredentials(self.cfg["service_account"], self.cfg["key_file"])
        ee.Initialize(credentials, project=self.cfg["project"])
        
        # 3. Definição da Região (via geemap) e Coleção
        self.region = geemap.shp_to_ee(str(self.shp_path)).geometry()
        self.collection_base = ee.ImageCollection(self.cfg["collection"]).select(self.cfg["selection"])
        print("Shapefile carregado.\n")
        
        self._limpar_arquivos_gcs()
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

    def _limpar_arquivos_gcs(self):
        """Remove os arquivos temporários _gcs gerados pelo geemap."""
        print("Limpando arquivos temporários _gcs...")
        stem_gcs = self.shp_path.stem + "_gcs"
        removidos = []
        
        for ext in [".shp", ".dbf", ".prj", ".shx", ".cpg", ".qpj"]:
            arquivo_gcs = self.shp_path.parent / (stem_gcs + ext)
            if arquivo_gcs.exists():
                arquivo_gcs.unlink()
                removidos.append(arquivo_gcs.name)
                
        if removidos:
            print(f"  Arquivos _gcs removidos: {', '.join(removidos)}\n")
        else:
            print("  Nenhum arquivo _gcs encontrado para remover.\n")

    # --- LÓGICA DE DOWNLOAD ---

    def process_month(self, year: int, month: int, filepath: Path) -> dict:
        """Filtra a coleção para o mês e exporta o raster usando geemap."""
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year+1}-01-01" if month == 12 else f"{year}-{month+1:02d}-01"
        
        col = self.collection_base.filterDate(start_date, end_date)
        if col.size().getInfo() == 0:
            return {"status": "sem_dado", "ts": datetime.now().isoformat()}

        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        geemap.ee_export_image(
            col.first().clip(self.region),
            filename=str(filepath),
            scale=self.cfg["scale"],
            region=self.region,
            crs=self.cfg["crs"],
            file_per_band=False,
        )

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

            for tentativa in range(self.cfg["max_retries"]):
                try:
                    res = self.process_month(y, m, filepath)
                    self.log_data[chave] = res
                    if res["status"] == "ok":
                        print(f"ok ({res.get('size_kb', 0):.0f} KB)")
                        sucessos += 1
                    else:
                        print("sem dado no GEE — pulando")
                    break # Sucesso, sai do loop de tentativas
                except Exception as e:
                    if tentativa < self.cfg["max_retries"] - 1:
                        print(f"Erro (tentativa {tentativa+1}). Retentando...", end=" ", flush=True)
                        time.sleep(self.cfg["pause_sec"] * 2)
                    else:
                        print(f"ERRO FINAL — {e}")
                        self.log_data[chave] = {"status": "erro", "ts": datetime.now().isoformat(), "msg": str(e)}
                        erros.append((y, m, str(e)))

            self._save_log()
            time.sleep(self.cfg["pause_sec"])

        print("\n" + "=" * 55 + f"\n  Baixados: {sucessos} | Erros: {len(erros)}\n" + "=" * 55)

if __name__ == "__main__":
    GEEDownloaderEstadual().run()