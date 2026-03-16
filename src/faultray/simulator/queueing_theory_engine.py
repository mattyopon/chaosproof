"""Queueing Theory Engine — models infrastructure components as queues.

Applies classical queueing theory to predict bottlenecks, saturation points,
and capacity limits in infrastructure dependency graphs.

Key techniques:

1. **M/M/1 Queue** — single-server Markovian queue analysis.  Computes
   utilisation (rho), average queue length (L), and average wait time (W).
   *Difference from capacity_engine.py*: capacity planning uses heuristic
   thresholds; M/M/1 gives closed-form steady-state metrics grounded in
   Kendall notation.

2. **M/M/c Queue** — multi-server extension using the Erlang-C formula.
   Accounts for replica counts when modelling service capacity.
   *Difference from M/M/1*: M/M/c distributes arrivals across *c* servers,
   yielding lower wait times and a fundamentally different probability of
   queueing (Erlang-C ≠ simple rho).

3. **Little's Law** — L = λW.  A universal relationship that does *not*
   depend on arrival/service distributions.

4. **Bottleneck Analysis** — maps each InfraGraph component to a queue,
   computes per-component utilisation and wait times, and ranks them.

5. **Saturation Prediction** — scales arrival rates by a traffic multiplier
   and identifies which components saturate first.

All implementations use **standard library only** (math).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph


# =====================================================================
# Result dataclasses
# =====================================================================

@dataclass
class MM1Result:
    """Steady-state metrics for an M/M/1 queue.

    Attributes:
        arrival_rate: Mean arrival rate (lambda).
        service_rate: Mean service rate (mu).
        utilization: Server utilisation rho = lambda / mu.
        avg_queue_length: Expected number of customers in system (L).
        avg_wait_time: Expected time a customer spends in system (W).
        avg_queue_wait: Expected time waiting in the queue (Wq).
        avg_queue_only_length: Expected number waiting in the queue (Lq).
        stable: Whether the system is stable (rho < 1).
    """

    arrival_rate: float = 0.0
    service_rate: float = 0.0
    utilization: float = 0.0
    avg_queue_length: float = 0.0
    avg_wait_time: float = 0.0
    avg_queue_wait: float = 0.0
    avg_queue_only_length: float = 0.0
    stable: bool = True


@dataclass
class MMcResult:
    """Steady-state metrics for an M/M/c queue (Erlang-C).

    Attributes:
        arrival_rate: Mean arrival rate (lambda).
        service_rate: Per-server service rate (mu).
        servers: Number of parallel servers (c).
        utilization: Per-server utilisation rho = lambda / (c * mu).
        erlang_c: Probability that an arriving customer must wait (C(c, a)).
        avg_queue_length: Expected number in system (L).
        avg_wait_time: Expected time in system (W).
        avg_queue_wait: Expected wait in queue only (Wq).
        stable: Whether rho < 1.
    """

    arrival_rate: float = 0.0
    service_rate: float = 0.0
    servers: int = 1
    utilization: float = 0.0
    erlang_c: float = 0.0
    avg_queue_length: float = 0.0
    avg_wait_time: float = 0.0
    avg_queue_wait: float = 0.0
    stable: bool = True


@dataclass
class BottleneckEntry:
    """A single component's queueing metrics for bottleneck ranking.

    Attributes:
        component_id: The component identifier.
        component_name: Human-readable name.
        arrival_rate: Estimated arrival rate (requests/sec).
        service_rate: Estimated service rate (requests/sec).
        servers: Number of replicas serving as parallel servers.
        utilization: Per-server utilisation.
        avg_wait_time: Expected time in system.
        is_saturated: True if utilisation >= 1.0 (unstable).
        rank: Bottleneck rank (1 = worst).
    """

    component_id: str = ""
    component_name: str = ""
    arrival_rate: float = 0.0
    service_rate: float = 0.0
    servers: int = 1
    utilization: float = 0.0
    avg_wait_time: float = 0.0
    is_saturated: bool = False
    rank: int = 0


@dataclass
class SaturationPrediction:
    """Prediction of queue saturation under increased traffic.

    Attributes:
        traffic_multiplier: The factor applied to arrival rates.
        saturated_components: Components that would become unstable.
        component_metrics: Per-component metrics at the projected load.
        first_to_saturate: The component that saturates first (lowest
            headroom).
    """

    traffic_multiplier: float = 1.0
    saturated_components: list[str] = field(default_factory=list)
    component_metrics: list[BottleneckEntry] = field(default_factory=list)
    first_to_saturate: str = ""


# =====================================================================
# Engine
# =====================================================================

class QueueingTheoryEngine:
    """Models infrastructure components as queueing systems.

    Each component is treated as an M/M/1 or M/M/c queue where:
    - arrival_rate (lambda) is derived from current network connections
      and the component's max_rps capacity.
    - service_rate (mu) is derived from max_rps / replicas as the
      per-server throughput.
    - servers (c) equals the component's replica count.

    This enables closed-form analysis of wait times, queue lengths, and
    utilisation — complementing the simulation-based approaches in
    CascadeEngine and DynamicEngine.
    """

    def __init__(self, graph: InfraGraph | None = None) -> None:
        self.graph = graph

    # -----------------------------------------------------------------
    # M/M/1
    # -----------------------------------------------------------------

    def mm1_queue(self, arrival_rate: float, service_rate: float) -> MM1Result:
        """Analyse a single-server M/M/1 queue.

        Parameters:
            arrival_rate: Mean arrival rate lambda (requests/sec).
            service_rate: Mean service rate mu (requests/sec).

        Returns:
            MM1Result with utilisation, queue length, and wait times.

        The system is *stable* only when rho = lambda/mu < 1.  When
        unstable the queue grows without bound; we report rho and mark
        ``stable=False`` but set L and W to infinity.
        """

        if service_rate <= 0:
            return MM1Result(
                arrival_rate=arrival_rate,
                service_rate=service_rate,
                utilization=float("inf"),
                avg_queue_length=float("inf"),
                avg_wait_time=float("inf"),
                avg_queue_wait=float("inf"),
                avg_queue_only_length=float("inf"),
                stable=False,
            )

        rho = arrival_rate / service_rate

        if rho >= 1.0:
            return MM1Result(
                arrival_rate=arrival_rate,
                service_rate=service_rate,
                utilization=rho,
                avg_queue_length=float("inf"),
                avg_wait_time=float("inf"),
                avg_queue_wait=float("inf"),
                avg_queue_only_length=float("inf"),
                stable=False,
            )

        # Steady-state formulae
        L = rho / (1.0 - rho)
        W = 1.0 / (service_rate - arrival_rate)
        Wq = rho / (service_rate - arrival_rate)
        Lq = rho * rho / (1.0 - rho)

        return MM1Result(
            arrival_rate=arrival_rate,
            service_rate=service_rate,
            utilization=rho,
            avg_queue_length=L,
            avg_wait_time=W,
            avg_queue_wait=Wq,
            avg_queue_only_length=Lq,
            stable=True,
        )

    # -----------------------------------------------------------------
    # M/M/c  (Erlang-C)
    # -----------------------------------------------------------------

    def mmc_queue(
        self, arrival_rate: float, service_rate: float, servers: int
    ) -> MMcResult:
        """Analyse a multi-server M/M/c queue using the Erlang-C formula.

        Parameters:
            arrival_rate: Mean arrival rate lambda.
            service_rate: Per-server service rate mu.
            servers: Number of identical parallel servers c.

        Returns:
            MMcResult including the Erlang-C probability of waiting.

        The Erlang-C probability C(c, a) represents the chance that an
        arriving customer finds all servers busy and must wait.  It is
        computed via the standard recursive formula to avoid factorial
        overflow.
        """

        c = max(1, servers)

        if service_rate <= 0:
            return MMcResult(
                arrival_rate=arrival_rate,
                service_rate=service_rate,
                servers=c,
                utilization=float("inf"),
                stable=False,
            )

        a = arrival_rate / service_rate  # offered load in Erlangs
        rho = a / c  # per-server utilisation

        if rho >= 1.0:
            return MMcResult(
                arrival_rate=arrival_rate,
                service_rate=service_rate,
                servers=c,
                utilization=rho,
                erlang_c=1.0,
                avg_queue_length=float("inf"),
                avg_wait_time=float("inf"),
                avg_queue_wait=float("inf"),
                stable=False,
            )

        # Compute Erlang-C using iterative Poisson sum to avoid factorial overflow
        # P0 = 1 / [ sum_{k=0}^{c-1} a^k/k! + a^c/c! * 1/(1-rho) ]
        poisson_sum = 0.0
        term = 1.0  # a^0 / 0! = 1
        for k in range(c):
            poisson_sum += term
            term *= a / (k + 1)
        # term is now a^c / c!
        last_term = term / (1.0 - rho)
        p0 = 1.0 / (poisson_sum + last_term)

        # C(c, a) = (a^c / c!) * (1/(1-rho)) * P0
        erlang_c = last_term * p0

        # Performance metrics
        Wq = erlang_c / (c * service_rate * (1.0 - rho))
        W = Wq + 1.0 / service_rate
        Lq = arrival_rate * Wq
        L = arrival_rate * W

        return MMcResult(
            arrival_rate=arrival_rate,
            service_rate=service_rate,
            servers=c,
            utilization=rho,
            erlang_c=erlang_c,
            avg_queue_length=L,
            avg_wait_time=W,
            avg_queue_wait=Wq,
            stable=True,
        )

    # -----------------------------------------------------------------
    # Little's Law
    # -----------------------------------------------------------------

    @staticmethod
    def littles_law(arrival_rate: float, avg_time_in_system: float) -> float:
        """Apply Little's Law: L = lambda * W.

        Parameters:
            arrival_rate: Mean arrival rate lambda.
            avg_time_in_system: Mean time a customer spends in the
                system (W).

        Returns:
            Average number of customers in the system (L).

        Little's Law is distribution-free — it holds for *any* queueing
        discipline and arrival/service distribution, making it a
        universal cross-check for simulation results.
        """

        return arrival_rate * avg_time_in_system

    # -----------------------------------------------------------------
    # Bottleneck Analysis
    # -----------------------------------------------------------------

    def analyze_bottleneck(self, graph: InfraGraph | None = None) -> list[BottleneckEntry]:
        """Model each component as a queue and identify bottlenecks.

        Parameters:
            graph: The infrastructure graph (uses self.graph if None).

        Returns:
            List of BottleneckEntry sorted by utilisation descending
            (rank 1 = most likely bottleneck).

        Arrival rate is estimated from ``metrics.network_connections``
        divided by ``capacity.timeout_seconds`` (as a rough requests/sec
        proxy).  Service rate is ``capacity.max_rps / replicas``.
        """

        g = graph or self.graph
        if g is None:
            return []

        entries: list[BottleneckEntry] = []

        for comp in g.components.values():
            # Estimate arrival rate from current connections and timeout
            timeout = comp.capacity.timeout_seconds
            if timeout <= 0:
                timeout = 1.0
            arrival_rate = comp.metrics.network_connections / timeout

            # Service rate: max requests per second per replica
            servers = max(1, comp.replicas)
            service_rate_total = float(comp.capacity.max_rps) if comp.capacity.max_rps > 0 else 1.0
            service_rate_per_server = service_rate_total / servers

            # Use M/M/c if multiple replicas, M/M/1 otherwise
            if servers > 1:
                result = self.mmc_queue(arrival_rate, service_rate_per_server, servers)
                util = result.utilization
                wait = result.avg_wait_time if result.stable else float("inf")
            else:
                result = self.mm1_queue(arrival_rate, service_rate_per_server)
                util = result.utilization
                wait = result.avg_wait_time if result.stable else float("inf")

            entries.append(BottleneckEntry(
                component_id=comp.id,
                component_name=comp.name,
                arrival_rate=arrival_rate,
                service_rate=service_rate_per_server,
                servers=servers,
                utilization=util,
                avg_wait_time=wait,
                is_saturated=util >= 1.0,
            ))

        # Sort by utilisation descending and assign ranks
        entries.sort(key=lambda e: e.utilization, reverse=True)
        for i, entry in enumerate(entries):
            entry.rank = i + 1

        return entries

    # -----------------------------------------------------------------
    # Saturation Prediction
    # -----------------------------------------------------------------

    def predict_saturation(
        self, graph: InfraGraph | None = None, traffic_multiplier: float = 2.0
    ) -> SaturationPrediction:
        """Predict which components saturate under increased traffic.

        Parameters:
            graph: The infrastructure graph (uses self.graph if None).
            traffic_multiplier: Factor to scale arrival rates by.

        Returns:
            SaturationPrediction with per-component projected metrics
            and the list of components that would become unstable.

        This is a forward-looking *what-if* analysis: "if traffic
        doubles, which queues overflow first?"  Complements
        CascadeEngine.simulate_traffic_spike which uses utilisation
        thresholds, whereas this method uses queueing-theoretic
        stability (rho < 1).
        """

        g = graph or self.graph
        if g is None:
            return SaturationPrediction(traffic_multiplier=traffic_multiplier)

        entries: list[BottleneckEntry] = []
        saturated: list[str] = []
        min_headroom = float("inf")
        first_to_saturate = ""

        for comp in g.components.values():
            timeout = comp.capacity.timeout_seconds
            if timeout <= 0:
                timeout = 1.0
            base_arrival = comp.metrics.network_connections / timeout
            arrival_rate = base_arrival * traffic_multiplier

            servers = max(1, comp.replicas)
            service_rate_total = float(comp.capacity.max_rps) if comp.capacity.max_rps > 0 else 1.0
            service_rate_per_server = service_rate_total / servers

            if servers > 1:
                result = self.mmc_queue(arrival_rate, service_rate_per_server, servers)
                util = result.utilization
                wait = result.avg_wait_time if result.stable else float("inf")
            else:
                result = self.mm1_queue(arrival_rate, service_rate_per_server)
                util = result.utilization
                wait = result.avg_wait_time if result.stable else float("inf")

            is_sat = util >= 1.0
            if is_sat:
                saturated.append(comp.id)

            # Headroom = how far from saturation (lower = closer)
            headroom = 1.0 - util
            if headroom < min_headroom:
                min_headroom = headroom
                first_to_saturate = comp.id

            entries.append(BottleneckEntry(
                component_id=comp.id,
                component_name=comp.name,
                arrival_rate=arrival_rate,
                service_rate=service_rate_per_server,
                servers=servers,
                utilization=util,
                avg_wait_time=wait,
                is_saturated=is_sat,
            ))

        entries.sort(key=lambda e: e.utilization, reverse=True)
        for i, entry in enumerate(entries):
            entry.rank = i + 1

        return SaturationPrediction(
            traffic_multiplier=traffic_multiplier,
            saturated_components=saturated,
            component_metrics=entries,
            first_to_saturate=first_to_saturate,
        )
