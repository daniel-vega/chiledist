"""
chiledist/persistence.py
========================
Persistencia reproducible de corridas de redistritaje.

Provee:
    new_run_id()            — UUID v4 para identificar una corrida
    sha256_file(path)       — hash del archivo de entrada
    get_package_versions()  — versiones de paquetes relevantes
    save_assignments_parquet(...)  — raw assignments a Parquet
    build_run_manifest(...)        — construye el diccionario del manifiesto
    save_run_manifest(...)         — escribe run_manifest.json
    PlanEnsemble               — contenedor con save/load/filter/sample

Formato assignments.parquet
----------------------------
    run_id   : string   UUID de la corrida
    scenario : string   nombre del ScenarioConfig
    chain_id : int8     0 para cadena única; 0..K-1 para multi-cadena
    draw     : int32    número de paso en la cadena
    unit_id  : string   ID_DIST o CUT según decision_unit
    district : int16    etiqueta del distrito asignado
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def new_run_id() -> str:
    """Genera un UUID v4 para identificar unívocamente una corrida."""
    return str(uuid.uuid4())


def sha256_file(path: str) -> str:
    """SHA-256 del archivo en `path`. Retorna '' si el archivo no existe."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def get_package_versions() -> Dict[str, str]:
    """Retorna un dict {paquete: versión} de los paquetes clave del entorno."""
    packages = [
        "geopandas", "gerrychain", "numpy", "pandas", "scipy",
        "networkx", "shapely", "pyproj", "libpysal", "scikit_learn",
        "pyarrow",
    ]
    versions: Dict[str, str] = {}
    for pkg in packages:
        try:
            m = __import__(pkg.replace("-", "_"))
            versions[pkg] = getattr(m, "__version__", "unknown")
        except ImportError:
            versions[pkg] = "not_installed"
    return versions


# ──────────────────────────────────────────────────────────────────────────────
# Guardar assignments.parquet
# ──────────────────────────────────────────────────────────────────────────────

def save_assignments_parquet(
    planes: List[dict],
    id_map: Dict,
    run_id: str,
    scenario_name: str,
    output_dir: str,
    chain_id: int = 0,
) -> str:
    """
    Serializa los raw assignments a Parquet.

    Parameters
    ----------
    planes : list[dict]
        Lista de planes; cada plan es {node_or_unit_id: district}.
    id_map : dict
        Mapeo {node_idx: unit_id} para traducir claves de nodo a IDs reales.
        Si las claves ya son unit IDs pásalo como {uid: uid}.
    run_id : str
        UUID de la corrida.
    scenario_name : str
        Nombre del ScenarioConfig.
    output_dir : str
        Directorio donde escribir assignments.parquet.
    chain_id : int
        Índice de la cadena (0 para cadena única).

    Returns
    -------
    str  Ruta del archivo generado, o '' si no hay planes.
    """
    if not planes:
        return ""

    try:
        import pyarrow  # noqa: F401
    except ImportError:
        raise ImportError(
            "pyarrow no está instalado. "
            "Instala con: pip install 'pyarrow>=14.0.0'"
        )

    rows = []
    for draw, assignment in enumerate(planes):
        for node, district in assignment.items():
            unit_id = id_map.get(node, node)
            if unit_id is None:
                continue
            rows.append({
                "run_id":   run_id,
                "scenario": scenario_name,
                "chain_id": chain_id,
                "draw":     draw,
                "unit_id":  str(unit_id),
                "district": int(district),
            })

    if not rows:
        return ""

    df = pd.DataFrame(rows)
    df["chain_id"] = df["chain_id"].astype("int8")
    df["draw"]     = df["draw"].astype("int32")
    df["district"] = df["district"].astype("int16")

    out_path = Path(output_dir) / "assignments.parquet"
    df.to_parquet(str(out_path), index=False, compression="snappy")

    n_draws = df["draw"].nunique()
    n_units = df["unit_id"].nunique()
    print(f"  Guardado: assignments.parquet "
          f"({n_draws:,} draws × {n_units:,} unidades = {len(df):,} filas)")
    return str(out_path)


# ──────────────────────────────────────────────────────────────────────────────
# Run manifest
# ──────────────────────────────────────────────────────────────────────────────

def build_run_manifest(
    run_id: str,
    timestamp_start: str,
    timestamp_end: str,
    scenario,
    pop_source: str,
    pop_col_effective: str,
    pop_tolerance_requested: float,
    pop_tolerance_effective: float,
    pop_tolerance_fallback_used: bool,
    n_steps_requested: int,
    n_steps_executed: int,
    n_steps_warmup: int,
    n_plans_generated: int,
    n_plans_valid: int,
    region_code: int,
    region_name: str,
    n_units: int,
    n_islands_found: int = 0,
    n_islands_connected: int = 0,
    input_files: Optional[Dict[str, str]] = None,
    extra: Optional[Dict] = None,
) -> dict:
    """
    Construye el diccionario completo del manifiesto de una corrida.

    Parameters
    ----------
    scenario : ScenarioConfig
        Configuración completa del escenario.
    input_files : dict {path: sha256}
        Hashes de los archivos de entrada (shapefiles, CSVs de población).
    extra : dict, opcional
        Campos adicionales a incluir en el manifiesto.

    Returns
    -------
    dict  Serializable a JSON vía json.dump(..., default=str).
    """
    from . import __version__ as chiledist_version

    import dataclasses as _dc
    scenario_dict = _dc.asdict(scenario) if hasattr(scenario, "__dataclass_fields__") else {}

    manifest: dict = {
        "run_id":             run_id,
        "chiledist_version":  chiledist_version,
        "timestamp_start":    timestamp_start,
        "timestamp_end":      timestamp_end,

        "scenario": {
            **scenario_dict,
            "pop_source":                  pop_source,
            "pop_col_effective":           pop_col_effective,
            "pop_tolerance_requested":     pop_tolerance_requested,
            "pop_tolerance_effective":     pop_tolerance_effective,
            "pop_tolerance_fallback_used": pop_tolerance_fallback_used,
        },

        "data": {
            "region_code":         region_code,
            "region_name":         region_name,
            "n_units":             n_units,
            "n_islands_found":     n_islands_found,
            "n_islands_connected": n_islands_connected,
            "input_files":         input_files or {},
        },

        "algorithm": {
            "sampler":           "recom",
            "n_steps_requested": n_steps_requested,
            "n_steps_executed":  n_steps_executed,
            "n_steps_warmup":    n_steps_warmup,
            "n_plans_generated": n_plans_generated,
            "n_plans_valid":     n_plans_valid,
        },

        "environment": {
            "python_version": (f"{sys.version_info.major}."
                               f"{sys.version_info.minor}."
                               f"{sys.version_info.micro}"),
            "platform":       platform.platform(),
            "packages":       get_package_versions(),
        },

        "outputs": {
            "assignments_parquet": "assignments.parquet",
            "ensemble_stats_csv":  "ensemble_stats.csv",
            "chain_metrics_csv":   "metricas_cadena.csv",
        },
    }

    if extra:
        manifest.update(extra)

    return manifest


def save_run_manifest(manifest: dict, output_dir: str) -> str:
    """Escribe run_manifest.json en output_dir. Retorna la ruta."""
    out_path = Path(output_dir) / "run_manifest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)
    rid = manifest.get("run_id", "?")
    print(f"  Guardado: run_manifest.json (run_id={rid[:8]}…)")
    return str(out_path)


# ──────────────────────────────────────────────────────────────────────────────
# PlanEnsemble
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PlanEnsemble:
    """
    Contenedor de un ensemble de planes de redistritaje con persistencia.

    Uso típico
    ----------
    >>> ensemble = PlanEnsemble.load("datos/R13/.../run_20260620_143201_550e8400")
    >>> valid = ensemble.filter(max_dev=5.0)
    >>> subsample = valid.sample(n=200, seed=42)

    Atributos
    ---------
    run_id : str
        UUID de la corrida.
    scenario_name : str
        Nombre del ScenarioConfig.
    assignments : pd.DataFrame
        Raw assignments (run_id, scenario, chain_id, draw, unit_id, district).
    stats : pd.DataFrame
        Métricas por plan (ensemble_stats.csv).
    chain_metrics : pd.DataFrame
        Métricas por paso de cadena (metricas_cadena.csv).
    manifest : dict
        Contenido de run_manifest.json.
    """

    run_id:        str
    scenario_name: str
    assignments:   pd.DataFrame
    stats:         pd.DataFrame
    chain_metrics: pd.DataFrame
    manifest:      dict = field(default_factory=dict)

    @property
    def n_draws(self) -> int:
        return int(self.assignments["draw"].nunique()) if not self.assignments.empty else 0

    @property
    def n_units(self) -> int:
        return int(self.assignments["unit_id"].nunique()) if not self.assignments.empty else 0

    def save(self, output_dir: str) -> None:
        """Escribe assignments.parquet + ensemble_stats.csv + metricas_cadena.csv + run_manifest.json."""
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            raise ImportError(
                "pyarrow no está instalado. "
                "Instala con: pip install 'pyarrow>=14.0.0'"
            )

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        self.assignments.to_parquet(str(out / "assignments.parquet"),
                                    index=False, compression="snappy")
        self.stats.to_csv(out / "ensemble_stats.csv", index=False)
        self.chain_metrics.to_csv(out / "metricas_cadena.csv", index=False)

        if self.manifest:
            with open(out / "run_manifest.json", "w", encoding="utf-8") as f:
                json.dump(self.manifest, f, ensure_ascii=False, indent=2, default=str)

        print(f"  PlanEnsemble guardado: {output_dir} "
              f"({self.n_draws:,} draws, {self.n_units:,} unidades)")

    @classmethod
    def load(cls, output_dir: str) -> "PlanEnsemble":
        """
        Lee un PlanEnsemble desde un directorio de run.

        El directorio debe contener al menos assignments.parquet.
        ensemble_stats.csv, metricas_cadena.csv y run_manifest.json son
        opcionales pero se cargan si existen.
        """
        out = Path(output_dir)
        parquet_path = out / "assignments.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(
                f"assignments.parquet no encontrado en {output_dir}"
            )

        assignments = pd.read_parquet(str(parquet_path))

        stats_path = out / "ensemble_stats.csv"
        stats = pd.read_csv(stats_path) if stats_path.exists() else pd.DataFrame()

        chain_path = out / "metricas_cadena.csv"
        chain_metrics = pd.read_csv(chain_path) if chain_path.exists() else pd.DataFrame()

        manifest: dict = {}
        manifest_path = out / "run_manifest.json"
        if manifest_path.exists():
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

        run_id = manifest.get("run_id", out.name)
        scenario_name = "unknown"
        if manifest:
            sc = manifest.get("scenario", {})
            scenario_name = sc.get("name", "unknown") if isinstance(sc, dict) else "unknown"
        if "scenario" in assignments.columns and not assignments.empty:
            scenario_name = assignments["scenario"].iloc[0]

        return cls(
            run_id=run_id,
            scenario_name=scenario_name,
            assignments=assignments,
            stats=stats,
            chain_metrics=chain_metrics,
            manifest=manifest,
        )

    def filter(
        self,
        max_dev: Optional[float] = None,
        min_pp: Optional[float] = None,
        max_cut_edges: Optional[int] = None,
    ) -> "PlanEnsemble":
        """
        Filtra planes por criterios de calidad.

        Returns
        -------
        PlanEnsemble  Nueva instancia con solo los draws que cumplen los criterios.
        """
        if self.stats.empty or "plan_id" not in self.stats.columns:
            return self

        mask = pd.Series(True, index=self.stats.index)
        if max_dev is not None and "max_dev_pob_pct" in self.stats.columns:
            mask &= self.stats["max_dev_pob_pct"] <= max_dev
        if min_pp is not None and "pp_promedio" in self.stats.columns:
            mask &= self.stats["pp_promedio"].fillna(0) >= min_pp
        if max_cut_edges is not None and "cut_edges" in self.stats.columns:
            mask &= self.stats["cut_edges"] <= max_cut_edges

        valid_draws = set(self.stats.loc[mask, "plan_id"].tolist())
        filtered_assignments = self.assignments[
            self.assignments["draw"].isin(valid_draws)
        ].copy()

        return PlanEnsemble(
            run_id=self.run_id,
            scenario_name=self.scenario_name,
            assignments=filtered_assignments,
            stats=self.stats.loc[mask].copy().reset_index(drop=True),
            chain_metrics=self.chain_metrics,
            manifest=self.manifest,
        )

    def sample(self, n: int, seed: int = 0) -> "PlanEnsemble":
        """
        Subsample reproducible de n planes.

        Parameters
        ----------
        n : int
            Número de planes a retener. Si n >= n_draws, retorna self.
        seed : int
            Semilla para reproducibilidad.
        """
        if n >= self.n_draws:
            return self

        rng = np.random.default_rng(seed)
        all_draws = self.assignments["draw"].unique()
        sampled_draws = set(rng.choice(all_draws, size=n, replace=False).tolist())

        filtered_assignments = self.assignments[
            self.assignments["draw"].isin(sampled_draws)
        ].copy()

        if not self.stats.empty and "plan_id" in self.stats.columns:
            filtered_stats = self.stats[
                self.stats["plan_id"].isin(sampled_draws)
            ].copy().reset_index(drop=True)
        else:
            filtered_stats = self.stats

        return PlanEnsemble(
            run_id=self.run_id,
            scenario_name=self.scenario_name,
            assignments=filtered_assignments,
            stats=filtered_stats,
            chain_metrics=self.chain_metrics,
            manifest=self.manifest,
        )

    def __repr__(self) -> str:
        return (
            f"PlanEnsemble("
            f"run_id={self.run_id[:8]}…, "
            f"scenario={self.scenario_name!r}, "
            f"draws={self.n_draws:,}, "
            f"units={self.n_units:,})"
        )
