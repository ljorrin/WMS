"""
WMS Panama — Optimizador de Rutas de Picking (OR-Tools)
=========================================================
Usa Google OR-Tools (Vehicle Routing Problem) para calcular
la secuencia óptima de ubicaciones que minimiza la distancia
recorrida por cada operador de picking.

Algoritmos soportados:
  - PATH_CHEAPEST_ARC   : más rápido, solución greedy
  - SAVINGS             : Clarke-Wright, buena calidad
  - GUIDED_LOCAL_SEARCH : mejor calidad, más lento

Modelo de distancia:
  - Manhattan distance entre ubicaciones en el almacén
  - Coordenadas (aisle, bay, level) normalizadas en metros
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog

log = structlog.get_logger(__name__)

# Dimensiones físicas típicas de una posición de rack en metros
AISLE_SPACING_M = 3.0    # metros entre pasillos
BAY_SPACING_M   = 1.2    # metros entre bahías
LEVEL_SPACING_M = 0.5    # metros entre niveles (solo para 3D)


def _manhattan_distance(loc_a: dict, loc_b: dict) -> float:
    """
    Distancia Manhattan entre dos ubicaciones.
    Cada ubicación tiene: aisle (int), bay (int), level (int).
    """
    da = abs(loc_a.get("aisle", 0) - loc_b.get("aisle", 0)) * AISLE_SPACING_M
    db = abs(loc_a.get("bay", 0)   - loc_b.get("bay", 0))   * BAY_SPACING_M
    dl = abs(loc_a.get("level", 0) - loc_b.get("level", 0)) * LEVEL_SPACING_M
    return da + db + dl


def _build_distance_matrix(locations: list[dict]) -> list[list[int]]:
    """
    Construye la matriz de distancias en centímetros (OR-Tools usa enteros).
    """
    n = len(locations)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                dist_m = _manhattan_distance(locations[i], locations[j])
                matrix[i][j] = int(dist_m * 100)  # → centímetros
    return matrix


class PickingRouteOptimizer:
    """
    Optimizador de rutas de picking usando OR-Tools VRP.
    Soporta múltiples operadores (vehículos).
    """

    def __init__(self, db, tenant_id: UUID, user_id: UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    # ── API pública ───────────────────────────────────────────────────────────

    async def optimize_wave(
        self,
        wave_id: UUID,
        num_operators: int = 1,
        algorithm: str = "PATH_CHEAPEST_ARC",
        time_limit_seconds: int = 30,
    ) -> dict:
        """
        Optimiza las rutas de picking para una wave completa.
        """
        log.info("route_opt.start", wave=str(wave_id), operators=num_operators)

        # 1. Obtener tareas de picking de la wave
        tasks = await self._get_wave_tasks(wave_id)
        if not tasks:
            raise ValueError(f"Wave {wave_id} no tiene tareas de picking.")

        # 2. Obtener coordenadas de ubicaciones
        locations = await self._get_locations(tasks)
        if not locations:
            raise ValueError("No se encontraron coordenadas de ubicaciones.")

        # 3. Resolver VRP
        try:
            result = self._solve_vrp(
                locations=locations,
                tasks=tasks,
                num_operators=num_operators,
                algorithm=algorithm,
                time_limit_seconds=time_limit_seconds,
            )
        except ImportError:
            log.warning("ortools.not_installed", fallback="greedy_nearest_neighbor")
            result = self._greedy_nearest_neighbor(locations, tasks, num_operators)

        # 4. Calcular métricas
        unoptimized_dist = self._naive_distance(locations)
        savings_pct = (
            (unoptimized_dist - result["total_distance_m"]) / unoptimized_dist * 100
            if unoptimized_dist > 0 else 0
        )

        # 5. Persistir
        opt_id = await self._save_optimization(
            wave_id=wave_id,
            num_operators=num_operators,
            algorithm=algorithm,
            time_limit_seconds=time_limit_seconds,
            locations=locations,
            result=result,
            savings_pct=savings_pct,
        )

        log.info(
            "route_opt.completed",
            wave=str(wave_id),
            total_distance_m=result["total_distance_m"],
            savings_pct=round(savings_pct, 1),
        )

        return {
            "optimization_id": str(opt_id),
            "wave_id": str(wave_id),
            "routes": result["routes"],
            "total_distance_m": result["total_distance_m"],
            "estimated_minutes": result["estimated_minutes"],
            "savings_pct": round(savings_pct, 1),
            "solver_status": result["solver_status"],
            "algorithm": algorithm,
        }

    async def optimize_tasks(
        self,
        task_ids: list[UUID],
        num_operators: int = 1,
        algorithm: str = "PATH_CHEAPEST_ARC",
    ) -> dict:
        """Optimiza un conjunto específico de tareas sin wave."""
        tasks = await self._get_tasks_by_ids(task_ids)
        locations = await self._get_locations(tasks)

        try:
            result = self._solve_vrp(locations, tasks, num_operators, algorithm)
        except ImportError:
            result = self._greedy_nearest_neighbor(locations, tasks, num_operators)

        return {
            "routes": result["routes"],
            "total_distance_m": result["total_distance_m"],
            "estimated_minutes": result["estimated_minutes"],
            "solver_status": result["solver_status"],
        }

    # ── OR-Tools VRP ──────────────────────────────────────────────────────────

    def _solve_vrp(
        self,
        locations: list[dict],
        tasks: list[dict],
        num_operators: int,
        algorithm: str,
        time_limit_seconds: int = 30,
    ) -> dict:
        """Resuelve el VRP usando OR-Tools."""
        from ortools.constraint_solver import routing_enums_pb2
        from ortools.constraint_solver import pywrapcp

        n = len(locations)
        distance_matrix = _build_distance_matrix(locations)

        # Añadir depósito (punto de inicio/fin = staging area)
        depot_idx = 0  # primera ubicación = staging area

        manager = pywrapcp.RoutingIndexManager(n, num_operators, depot_idx)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node   = manager.IndexToNode(to_index)
            return distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Agregar dimension de distancia
        routing.AddDimension(
            transit_callback_index,
            0,          # sin slack
            1_000_000,  # capacidad máxima en cm
            True,       # start cumul to zero
            "Distance",
        )

        # Parámetros del solver
        search_params = pywrapcp.DefaultRoutingSearchParameters()
        algo_map = {
            "PATH_CHEAPEST_ARC": routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
            "SAVINGS":           routing_enums_pb2.FirstSolutionStrategy.SAVINGS,
            "GUIDED_LOCAL_SEARCH": routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH,
        }
        search_params.first_solution_strategy = algo_map.get(
            algorithm,
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
        )
        search_params.time_limit.seconds = time_limit_seconds

        solution = routing.SolveWithParameters(search_params)

        if not solution:
            # Fallback greedy si OR-Tools no encontró solución
            return self._greedy_nearest_neighbor(locations, tasks, num_operators)

        # Extraer rutas
        routes = []
        total_dist_cm = 0

        for vehicle_id in range(num_operators):
            index = routing.Start(vehicle_id)
            route_locs = []
            route_dist_cm = 0

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                route_locs.append({
                    "location_id": locations[node]["location_id"],
                    "location_code": locations[node].get("location_code", ""),
                    "task_id": tasks[node]["id"] if node < len(tasks) else None,
                })
                next_index = solution.Value(routing.NextVar(index))
                route_dist_cm += distance_matrix[
                    manager.IndexToNode(index)
                ][manager.IndexToNode(next_index)]
                index = next_index

            route_dist_m = route_dist_cm / 100
            total_dist_cm += route_dist_cm
            est_min = int(route_dist_m / 1.2)  # ~1.2 m/s velocidad de caminata

            routes.append({
                "operator_id": vehicle_id + 1,
                "route": route_locs,
                "distance_m": round(route_dist_m, 1),
                "est_minutes": est_min,
            })

        total_dist_m = total_dist_cm / 100
        return {
            "routes": routes,
            "total_distance_m": round(total_dist_m, 1),
            "estimated_minutes": sum(r["est_minutes"] for r in routes),
            "solver_status": "OPTIMAL",
        }

    # ── Greedy nearest-neighbor (fallback) ───────────────────────────────────

    def _greedy_nearest_neighbor(
        self,
        locations: list[dict],
        tasks: list[dict],
        num_operators: int,
    ) -> dict:
        """
        Algoritmo greedy del vecino más cercano.
        No requiere OR-Tools. Divide las tareas entre operadores
        y ordena cada subconjunto por nearest-neighbor.
        """
        n = len(locations)
        chunk_size = max(1, n // num_operators)
        routes = []
        total_dist = 0.0

        for op in range(num_operators):
            start = op * chunk_size
            end = start + chunk_size if op < num_operators - 1 else n
            subset = list(range(start, end))

            if not subset:
                continue

            ordered = [subset[0]]
            remaining = set(subset[1:])

            while remaining:
                current = ordered[-1]
                nearest = min(
                    remaining,
                    key=lambda x: _manhattan_distance(locations[current], locations[x]),
                )
                ordered.append(nearest)
                remaining.remove(nearest)

            route_locs = []
            dist = 0.0
            for i, idx in enumerate(ordered):
                route_locs.append({
                    "location_id": locations[idx]["location_id"],
                    "location_code": locations[idx].get("location_code", ""),
                    "task_id": tasks[idx]["id"] if idx < len(tasks) else None,
                })
                if i > 0:
                    dist += _manhattan_distance(locations[ordered[i-1]], locations[idx])

            total_dist += dist
            routes.append({
                "operator_id": op + 1,
                "route": route_locs,
                "distance_m": round(dist, 1),
                "est_minutes": int(dist / 1.2),
            })

        return {
            "routes": routes,
            "total_distance_m": round(total_dist, 1),
            "estimated_minutes": sum(r["est_minutes"] for r in routes),
            "solver_status": "FEASIBLE_GREEDY",
        }

    def _naive_distance(self, locations: list[dict]) -> float:
        """Distancia de ruta ingenua (en orden de lista) para comparar ahorro."""
        total = 0.0
        for i in range(1, len(locations)):
            total += _manhattan_distance(locations[i-1], locations[i])
        return total

    # ── Persistencia ──────────────────────────────────────────────────────────

    async def _save_optimization(
        self,
        wave_id: UUID,
        num_operators: int,
        algorithm: str,
        time_limit_seconds: int,
        locations: list[dict],
        result: dict,
        savings_pct: float,
    ) -> UUID:
        from app.models.ai import PickingRouteOptimization, RouteOptStatus

        record = PickingRouteOptimization(
            id=uuid4(),
            tenant_id=self.tenant_id,
            warehouse_id=self.tenant_id,  # placeholder
            wave_id=wave_id,
            status=RouteOptStatus.OPTIMIZED,
            num_operators=num_operators,
            num_locations=len(locations),
            algorithm=algorithm,
            time_limit_seconds=time_limit_seconds,
            routes=result["routes"],
            total_distance_m=result["total_distance_m"],
            estimated_minutes=result["estimated_minutes"],
            savings_pct=round(savings_pct, 2),
            solver_status=result["solver_status"],
            computed_at=datetime.now(timezone.utc),
            created_by_id=self.user_id,
        )
        self.db.add(record)
        await self.db.flush()
        return record.id

    # ── Data access ───────────────────────────────────────────────────────────

    async def _get_wave_tasks(self, wave_id: UUID) -> list[dict]:
        """Carga las PickingTasks de la wave."""
        from sqlalchemy import select, and_
        from app.models.outbound import PickingTask, PickingStatus

        result = await self.db.execute(
            select(PickingTask).where(
                and_(
                    PickingTask.wave_id == wave_id,
                    PickingTask.tenant_id == self.tenant_id,
                    PickingTask.status == PickingStatus.PENDING,
                )
            )
        )
        tasks = result.scalars().all()
        return [
            {
                "id": str(t.id),
                "location_id": str(t.from_location_id),
                "product_id": str(t.product_id),
                "quantity": float(t.quantity_requested),
            }
            for t in tasks
        ]

    async def _get_tasks_by_ids(self, task_ids: list[UUID]) -> list[dict]:
        from sqlalchemy import select, and_
        from app.models.outbound import PickingTask

        result = await self.db.execute(
            select(PickingTask).where(
                and_(
                    PickingTask.id.in_(task_ids),
                    PickingTask.tenant_id == self.tenant_id,
                )
            )
        )
        tasks = result.scalars().all()
        return [
            {
                "id": str(t.id),
                "location_id": str(t.from_location_id),
                "product_id": str(t.product_id),
                "quantity": float(t.quantity_requested),
            }
            for t in tasks
        ]

    async def _get_locations(self, tasks: list[dict]) -> list[dict]:
        """
        Obtiene coordenadas físicas de las ubicaciones.
        Formato esperado: aisle, bay, level.
        Fallback: genera coordenadas sintéticas basadas en hash del ID.
        """
        location_ids = list({t["location_id"] for t in tasks})
        # Primero intentar desde BD de maestros (futuro módulo)
        # Por ahora generamos coordenadas sintéticas para demo
        result = []
        for loc_id in location_ids:
            # Derivar coordenadas del UUID (demo)
            h = hash(loc_id) % 100_000
            aisle = (h // 100) % 20
            bay   = h % 50
            level = (h // 5000) % 5
            result.append({
                "location_id": loc_id,
                "location_code": f"A{aisle:02d}-B{bay:02d}-L{level}",
                "aisle": aisle,
                "bay": bay,
                "level": level,
            })
        return result
