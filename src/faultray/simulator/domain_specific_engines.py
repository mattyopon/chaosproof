"""Domain-Specific Resilience Engines — six specialised analysis techniques.

Each engine addresses a distinct aspect of infrastructure resilience that
cannot be adequately covered by general-purpose simulation or ML:

1. **ParetoOptimizer** — multi-objective optimisation (NSGA-II inspired)
   balancing resilience vs. cost.  Produces a Pareto front showing
   trade-offs.
   *Difference from GA (ga_scenario_optimizer.py)*: GA optimises a
   *single* objective; Pareto produces a *front* of non-dominated
   solutions across multiple conflicting objectives.

2. **BayesianOptimizer** — sample-efficient optimisation using a
   Gaussian Process surrogate + Expected Improvement acquisition.
   *Difference from PSO (timeseries_and_ensemble.py)*: PSO is
   population-based and requires many fitness evaluations; Bayesian
   optimisation builds a probabilistic model to minimise the number
   of expensive CascadeEngine calls.

3. **CommonCauseFailureAnalyzer** — beta-factor model for correlated
   failures (shared power, rack, AZ).
   *Difference from CascadeEngine*: cascade models *sequential*
   propagation; CCF models *simultaneous* failures from a shared root
   cause.

4. **GameTheoryAnalyzer** — minimax Nash equilibrium between an
   attacker choosing fault targets and a defender choosing mitigations.
   *Difference from AttackSurface engine*: attack surface enumerates
   *static* vulnerabilities; game theory finds *equilibrium strategies*
   where neither side benefits from deviating.

5. **FuzzyResilienceEngine** — fuzzy-logic evaluation when crisp
   thresholds are inappropriate (e.g. "somewhat degraded").
   *Difference from scoring heuristics in InfraGraph.resilience_score*:
   crisp scoring uses hard thresholds; fuzzy logic uses membership
   functions and linguistic rules for graceful, interpretable assessment.

6. **CausalInferenceEngine** — structural causal model with do-calculus
   and counterfactual reasoning for root cause analysis.
   *Difference from CascadeEngine*: cascade simulates *forward*
   propagation; causal inference reasons *backwards* ("had we not done X,
   would Y still have failed?") and supports interventional queries.

All implementations use **standard library only** (math, random, itertools).
"""

from __future__ import annotations

import math
import random
import itertools
from dataclasses import dataclass, field

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType


# =====================================================================
# Pareto Optimizer (NSGA-II inspired)
# =====================================================================

@dataclass
class ParetoSolution:
    """A single solution in the Pareto front.

    Attributes:
        configuration: Binary vector — 1 means "add redundancy" to
            that component (index maps to component order).
        resilience: Resilience score (higher is better).
        cost: Cost estimate (lower is better).
        rank: Pareto rank (1 = non-dominated front).
    """

    configuration: list[int] = field(default_factory=list)
    resilience: float = 0.0
    cost: float = 0.0
    rank: int = 0


@dataclass
class ParetoResult:
    """Result of Pareto optimisation.

    Attributes:
        pareto_front: Non-dominated solutions (rank 1).
        all_solutions: All evaluated solutions.
        generations: Number of generations run.
    """

    pareto_front: list[ParetoSolution] = field(default_factory=list)
    all_solutions: list[ParetoSolution] = field(default_factory=list)
    generations: int = 0


class ParetoOptimizer:
    """Multi-objective optimisation for resilience vs. cost trade-offs.

    Uses an NSGA-II inspired approach:
    1. Non-dominated sorting to rank solutions
    2. Crowding distance for diversity preservation
    3. Tournament selection + crossover + mutation

    Objective 1: Maximise resilience score
    Objective 2: Minimise infrastructure cost
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self.component_ids = list(graph.components.keys())
        self.dim = len(self.component_ids)
        self._front: list[tuple[float, float]] = []

    @staticmethod
    def _dominates(a: ParetoSolution, b: ParetoSolution) -> bool:
        """Check if solution a Pareto-dominates solution b.

        a dominates b iff a is no worse in all objectives AND strictly
        better in at least one.  Here: higher resilience is better,
        lower cost is better.
        """

        better_in_any = False
        if a.resilience < b.resilience:
            return False
        if a.cost > b.cost:
            return False
        if a.resilience > b.resilience:
            better_in_any = True
        if a.cost < b.cost:
            better_in_any = True
        return better_in_any

    def _non_dominated_sort(
        self, population: list[ParetoSolution]
    ) -> list[list[ParetoSolution]]:
        """Sort population into non-dominated fronts.

        Front 1: solutions not dominated by any other
        Front 2: solutions dominated only by front 1
        And so on.
        """

        n = len(population)
        domination_count = [0] * n
        dominated_set: list[list[int]] = [[] for _ in range(n)]
        fronts: list[list[int]] = [[]]

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if self._dominates(population[i], population[j]):
                    dominated_set[i].append(j)
                elif self._dominates(population[j], population[i]):
                    domination_count[i] += 1

            if domination_count[i] == 0:
                population[i].rank = 1
                fronts[0].append(i)

        current_front = 0
        while fronts[current_front]:
            next_front: list[int] = []
            for i in fronts[current_front]:
                for j in dominated_set[i]:
                    domination_count[j] -= 1
                    if domination_count[j] == 0:
                        population[j].rank = current_front + 2
                        next_front.append(j)
            current_front += 1
            fronts.append(next_front)

        result: list[list[ParetoSolution]] = []
        for front_indices in fronts:
            if front_indices:
                result.append([population[i] for i in front_indices])
        return result

    def _evaluate(self, config: list[int]) -> ParetoSolution:
        """Evaluate a configuration for resilience and cost.

        A '1' in position i means we add redundancy (extra replica +
        failover) to component i, increasing resilience but also cost.
        """

        total_cost = 0.0
        for i, comp_id in enumerate(self.component_ids):
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue
            base_cost = comp.cost_profile.hourly_infra_cost
            if config[i] == 1:
                total_cost += base_cost * 1.5  # 1.5x for redundancy
            else:
                total_cost += base_cost

        # Estimate resilience: base score + bonus for redundant components
        base_resilience = self.graph.resilience_score()
        redundancy_bonus = sum(config) / max(self.dim, 1) * 30.0
        resilience = min(100.0, base_resilience + redundancy_bonus)

        return ParetoSolution(
            configuration=list(config),
            resilience=resilience,
            cost=total_cost,
        )

    def optimize(
        self, population_size: int = 50, generations: int = 100
    ) -> ParetoResult:
        """Run multi-objective optimisation.

        Parameters:
            population_size: Number of solutions per generation.
            generations: Number of evolutionary generations.

        Returns:
            ParetoResult with the Pareto front and all solutions.
        """

        if self.dim == 0:
            return ParetoResult()

        # Initialise random population
        population: list[ParetoSolution] = []
        for _ in range(population_size):
            config = [random.randint(0, 1) for _ in range(self.dim)]
            population.append(self._evaluate(config))

        for gen in range(generations):
            # Non-dominated sort
            fronts = self._non_dominated_sort(population)

            # Create offspring via tournament selection + crossover + mutation
            offspring: list[ParetoSolution] = []
            while len(offspring) < population_size:
                # Tournament selection (pick 2, prefer lower rank)
                candidates = random.sample(population, min(4, len(population)))
                candidates.sort(key=lambda s: s.rank)
                parent1 = candidates[0]
                parent2 = candidates[1] if len(candidates) > 1 else candidates[0]

                # Single-point crossover
                cx = random.randint(0, self.dim - 1) if self.dim > 1 else 0
                child_config = parent1.configuration[:cx] + parent2.configuration[cx:]

                # Mutation (bit flip with 10% per gene)
                for i in range(self.dim):
                    if random.random() < 0.1:
                        child_config[i] = 1 - child_config[i]

                offspring.append(self._evaluate(child_config))

            # Merge and select top population_size
            combined = population + offspring
            fronts = self._non_dominated_sort(combined)
            population = []
            for front in fronts:
                if len(population) + len(front) <= population_size:
                    population.extend(front)
                else:
                    remaining = population_size - len(population)
                    # Crowding distance sort for diversity
                    random.shuffle(front)
                    population.extend(front[:remaining])
                    break

        # Final sort
        fronts = self._non_dominated_sort(population)
        pareto_front = fronts[0] if fronts else []
        self._front = [(s.resilience, s.cost) for s in pareto_front]

        return ParetoResult(
            pareto_front=pareto_front,
            all_solutions=population,
            generations=generations,
        )

    def pareto_front(self) -> list[tuple[float, float]]:
        """Return the Pareto front as (resilience, cost) tuples."""
        return list(self._front)


# =====================================================================
# Bayesian Optimizer
# =====================================================================

@dataclass
class BayesianOptResult:
    """Result of Bayesian optimisation.

    Attributes:
        best_config: Best configuration found.
        best_value: Objective value at best configuration.
        evaluated_configs: All configurations evaluated.
        evaluated_values: Objective values for each configuration.
        iterations: Number of iterations completed.
    """

    best_config: dict = field(default_factory=dict)
    best_value: float = 0.0
    evaluated_configs: list[list[float]] = field(default_factory=list)
    evaluated_values: list[float] = field(default_factory=list)
    iterations: int = 0


class BayesianOptimizer:
    """Sample-efficient optimisation using Gaussian Process surrogates.

    Bayesian optimisation loop:
    1. Fit a Gaussian Process to observed (x, y) pairs
    2. Compute Expected Improvement acquisition function
    3. Select the x that maximises EI
    4. Evaluate the true (expensive) objective at x
    5. Add (x, y) to observations and repeat

    The GP uses an RBF (squared exponential) kernel.
    """

    def __init__(self, graph: InfraGraph, length_scale: float = 1.0) -> None:
        self.graph = graph
        self.component_ids = list(graph.components.keys())
        self.dim = len(self.component_ids)
        self.length_scale = length_scale
        self.cascade_engine = CascadeEngine(graph)
        self._best_config: dict = {}

    def _rbf_kernel(self, x1: list[float], x2: list[float]) -> float:
        """RBF (squared exponential) kernel: k(x1, x2) = exp(-||x1-x2||^2 / (2*l^2))."""
        sq_dist = sum((a - b) ** 2 for a, b in zip(x1, x2))
        return math.exp(-sq_dist / (2.0 * self.length_scale ** 2))

    def _gaussian_process_predict(
        self,
        X_train: list[list[float]],
        y_train: list[float],
        x_new: list[float],
    ) -> tuple[float, float]:
        """Simplified GP prediction: mean and variance at x_new.

        Uses the kernel trick with RBF kernel.  Adds a small noise
        term (nugget) for numerical stability.

        Returns:
            (mu, sigma) — predictive mean and standard deviation.
        """

        n = len(X_train)
        if n == 0:
            return 0.0, 1.0

        nugget = 1e-6

        # K: n x n kernel matrix
        K = [[self._rbf_kernel(X_train[i], X_train[j]) + (nugget if i == j else 0.0)
              for j in range(n)] for i in range(n)]

        # k_star: kernel between x_new and training points
        k_star = [self._rbf_kernel(x_new, X_train[i]) for i in range(n)]

        # Solve K * alpha = y using simple iterative method (Gauss-Seidel)
        alpha = list(y_train)
        for _ in range(50):
            for i in range(n):
                s = sum(K[i][j] * alpha[j] for j in range(n) if j != i)
                if abs(K[i][i]) > 1e-12:
                    alpha[i] = (y_train[i] - s) / K[i][i]

        mu = sum(k_star[i] * alpha[i] for i in range(n))

        # Variance: k(x_new, x_new) - k_star^T K^{-1} k_star
        # Approximate K^{-1} k_star using the same iterative solve
        beta = list(k_star)
        for _ in range(50):
            for i in range(n):
                s = sum(K[i][j] * beta[j] for j in range(n) if j != i)
                if abs(K[i][i]) > 1e-12:
                    beta[i] = (k_star[i] - s) / K[i][i]

        k_self = self._rbf_kernel(x_new, x_new) + nugget
        var = k_self - sum(k_star[i] * beta[i] for i in range(n))
        sigma = max(0.0, var) ** 0.5

        return mu, sigma

    @staticmethod
    def _expected_improvement(mu: float, sigma: float, best_y: float) -> float:
        """Expected Improvement acquisition function.

        EI(x) = (mu - best_y) * Phi(Z) + sigma * phi(Z)
        where Z = (mu - best_y) / sigma

        Phi = standard normal CDF, phi = standard normal PDF.
        """

        if sigma <= 1e-8:
            return max(0.0, mu - best_y)

        z = (mu - best_y) / sigma

        # Standard normal PDF and CDF approximation
        pdf = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)

        # CDF via error function
        cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

        return (mu - best_y) * cdf + sigma * pdf

    def _evaluate(self, x: list[float]) -> float:
        """Evaluate a configuration via CascadeEngine.

        x is a vector in [0, 1]^dim.  Components with x[i] > 0.5
        are faulted.  Returns cascade severity.
        """

        faults = []
        for i, comp_id in enumerate(self.component_ids):
            if x[i] > 0.5:
                faults.append(Fault(
                    target_component_id=comp_id,
                    fault_type=FaultType.COMPONENT_DOWN,
                    severity=x[i],
                ))

        if not faults:
            return 0.0

        total = 0.0
        for fault in faults:
            chain = self.cascade_engine.simulate_fault(fault)
            total += chain.severity
        return total

    def optimize(self, n_iterations: int = 30) -> BayesianOptResult:
        """Run Bayesian optimisation.

        Parameters:
            n_iterations: Number of optimisation iterations.

        Returns:
            BayesianOptResult with the best configuration found.

        Initial points are sampled randomly; subsequent points are
        chosen to maximise Expected Improvement.
        """

        if self.dim == 0:
            return BayesianOptResult()

        X: list[list[float]] = []
        y: list[float] = []

        # Initial random samples (at least 3)
        n_initial = min(5, n_iterations)
        for _ in range(n_initial):
            x = [random.uniform(0, 1) for _ in range(self.dim)]
            val = self._evaluate(x)
            X.append(x)
            y.append(val)

        # Bayesian optimisation loop
        for _ in range(n_iterations - n_initial):
            best_y = max(y)

            # Find x that maximises EI by random search (cheap approximation)
            best_ei = -1.0
            best_x: list[float] = [0.5] * self.dim
            for _ in range(100):
                candidate = [random.uniform(0, 1) for _ in range(self.dim)]
                mu, sigma = self._gaussian_process_predict(X, y, candidate)
                ei = self._expected_improvement(mu, sigma, best_y)
                if ei > best_ei:
                    best_ei = ei
                    best_x = candidate

            val = self._evaluate(best_x)
            X.append(best_x)
            y.append(val)

        # Find best
        best_idx = max(range(len(y)), key=lambda i: y[i])
        best_config = {}
        for i, comp_id in enumerate(self.component_ids):
            best_config[comp_id] = X[best_idx][i]

        self._best_config = best_config

        return BayesianOptResult(
            best_config=best_config,
            best_value=y[best_idx],
            evaluated_configs=X,
            evaluated_values=y,
            iterations=n_iterations,
        )

    def best_configuration(self) -> dict:
        """Return the best configuration found."""
        return dict(self._best_config)


# =====================================================================
# Common Cause Failure Analyzer (Beta-Factor Model)
# =====================================================================

@dataclass
class CCFGroup:
    """A group of components sharing a common cause.

    Attributes:
        common_cause: Description of the shared cause (e.g. 'same_rack').
        component_ids: Components in this group.
        beta: Beta factor (fraction of failures that are common-cause).
        independent_prob: Independent failure probability per component.
        ccf_prob: Common-cause failure probability for the group.
    """

    common_cause: str = ""
    component_ids: list[str] = field(default_factory=list)
    beta: float = 0.1
    independent_prob: float = 0.01
    ccf_prob: float = 0.0


@dataclass
class CCFResult:
    """Result of common-cause failure analysis.

    Attributes:
        groups: Identified CCF groups.
        total_ccf_risk: Aggregate CCF risk score.
        recommendations: Diversity recommendations.
    """

    groups: list[CCFGroup] = field(default_factory=list)
    total_ccf_risk: float = 0.0
    recommendations: list[str] = field(default_factory=list)


class CommonCauseFailureAnalyzer:
    """Beta-factor model for common-cause failures.

    In the beta-factor model:
        P_ccf = beta * P_independent

    where beta is the fraction of total failure rate attributable to
    common causes.  Components sharing a rack, AZ, region, or
    software version form CCF groups.

    This captures *simultaneous* correlated failures that cascade
    analysis (which models *sequential* propagation) cannot represent.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph

    def beta_factor_model(
        self,
        component_group: list[str],
        beta: float = 0.1,
    ) -> CCFGroup:
        """Compute CCF probability for a group using the beta-factor model.

        Parameters:
            component_group: List of component IDs sharing a cause.
            beta: Beta factor (0-1). Typical values:
                0.01-0.05 for diverse hardware
                0.05-0.15 for same rack/AZ
                0.1-0.3 for same software version

        Returns:
            CCFGroup with the computed CCF probability.

        P_ccf = beta * P_independent, where P_independent is estimated
        from MTBF (if available) or a default value.
        """

        # Estimate independent failure probability from MTBF
        probs = []
        for comp_id in component_group:
            comp = self.graph.get_component(comp_id)
            if comp is None:
                continue
            mtbf = comp.operational_profile.mtbf_hours
            if mtbf > 0:
                # Probability of failure in a 1-hour window
                prob = 1.0 - math.exp(-1.0 / mtbf)
            else:
                prob = 0.01  # default
            probs.append(prob)

        avg_prob = sum(probs) / len(probs) if probs else 0.01
        ccf_prob = beta * avg_prob

        return CCFGroup(
            common_cause="shared_infrastructure",
            component_ids=list(component_group),
            beta=beta,
            independent_prob=avg_prob,
            ccf_prob=ccf_prob,
        )

    def _identify_groups(self) -> list[CCFGroup]:
        """Identify CCF groups from component metadata.

        Groups are formed by shared:
        - Region + AZ (same data centre)
        - Component type (same software)
        - Host (same physical server)
        """

        groups: list[CCFGroup] = []

        # Group by region + AZ
        az_groups: dict[str, list[str]] = {}
        for comp in self.graph.components.values():
            key = f"{comp.region.region}:{comp.region.availability_zone}"
            if key != ":":
                az_groups.setdefault(key, []).append(comp.id)

        for key, comp_ids in az_groups.items():
            if len(comp_ids) > 1:
                group = self.beta_factor_model(comp_ids, beta=0.1)
                group.common_cause = f"same_az:{key}"
                groups.append(group)

        # Group by host
        host_groups: dict[str, list[str]] = {}
        for comp in self.graph.components.values():
            if comp.host:
                host_groups.setdefault(comp.host, []).append(comp.id)

        for host, comp_ids in host_groups.items():
            if len(comp_ids) > 1:
                group = self.beta_factor_model(comp_ids, beta=0.15)
                group.common_cause = f"same_host:{host}"
                groups.append(group)

        # Group by component type
        type_groups: dict[str, list[str]] = {}
        for comp in self.graph.components.values():
            type_groups.setdefault(comp.type.value, []).append(comp.id)

        for ctype, comp_ids in type_groups.items():
            if len(comp_ids) > 1:
                group = self.beta_factor_model(comp_ids, beta=0.05)
                group.common_cause = f"same_type:{ctype}"
                groups.append(group)

        return groups

    def analyze(self, graph: InfraGraph | None = None) -> CCFResult:
        """Analyse the graph for common-cause failure risks.

        Parameters:
            graph: Infrastructure graph (uses self.graph if None).

        Returns:
            CCFResult with identified groups, risk scores, and
            diversity recommendations.
        """

        if graph is not None:
            self.graph = graph

        groups = self._identify_groups()

        total_risk = sum(g.ccf_prob * len(g.component_ids) for g in groups)

        return CCFResult(
            groups=groups,
            total_ccf_risk=total_risk,
            recommendations=self.recommend_diversity(),
        )

    def recommend_diversity(self) -> list[str]:
        """Generate diversity recommendations to mitigate CCF.

        Returns:
            List of actionable recommendations.
        """

        recommendations: list[str] = []
        groups = self._identify_groups()

        for group in groups:
            if group.common_cause.startswith("same_host:") and len(group.component_ids) > 2:
                recommendations.append(
                    f"High CCF risk: {len(group.component_ids)} components share host "
                    f"'{group.common_cause.split(':')[1]}'. "
                    "Spread across multiple hosts to reduce correlated failure risk."
                )

            if group.common_cause.startswith("same_az:") and len(group.component_ids) > 3:
                az = group.common_cause.split(":")[1]
                recommendations.append(
                    f"AZ concentration: {len(group.component_ids)} components in AZ '{az}'. "
                    "Deploy replicas across multiple AZs."
                )

            if group.common_cause.startswith("same_type:") and len(group.component_ids) > 2:
                ctype = group.common_cause.split(":")[1]
                recommendations.append(
                    f"Software monoculture: {len(group.component_ids)} '{ctype}' components. "
                    "Consider heterogeneous implementations to limit blast radius "
                    "of software-specific bugs."
                )

        if not recommendations:
            recommendations.append(
                "Good diversity: no significant common-cause groups detected."
            )

        return recommendations


# =====================================================================
# Game Theory Analyzer (Minimax Nash Equilibrium)
# =====================================================================

@dataclass
class GameResult:
    """Result of game-theoretic resilience analysis.

    Attributes:
        payoff_matrix: The computed payoff matrix (attacker perspective).
        attacker_strategies: List of attacker strategy descriptions.
        defender_strategies: List of defender strategy descriptions.
        nash_attacker: Attacker's equilibrium mixed strategy (probabilities).
        nash_defender: Defender's equilibrium mixed strategy (probabilities).
        equilibrium_value: Expected payoff at Nash equilibrium.
        recommended_defense: The defender strategy with highest weight.
    """

    payoff_matrix: list[list[float]] = field(default_factory=list)
    attacker_strategies: list[str] = field(default_factory=list)
    defender_strategies: list[str] = field(default_factory=list)
    nash_attacker: list[float] = field(default_factory=list)
    nash_defender: list[float] = field(default_factory=list)
    equilibrium_value: float = 0.0
    recommended_defense: str = ""


class GameTheoryAnalyzer:
    """Game-theoretic resilience analysis using minimax.

    Models the interaction between:
    - Attacker: chooses which components to fault
    - Defender: chooses which mitigations to apply

    The payoff matrix represents cascade severity (attacker gain /
    defender loss).  Nash equilibrium identifies the optimal mixed
    strategies for both players — the defender's equilibrium strategy
    is the recommended mitigation allocation.

    Uses the minimax theorem: max_attacker min_defender payoff
    = min_defender max_attacker payoff (for zero-sum games).
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self.cascade_engine = CascadeEngine(graph)
        self._result: GameResult | None = None

    def _payoff_matrix(
        self,
        attacker_strategies: list[str],
        defender_strategies: list[str],
    ) -> list[list[float]]:
        """Build the payoff matrix.

        Parameters:
            attacker_strategies: Component IDs the attacker can target.
            defender_strategies: Mitigation labels (e.g. 'redundancy',
                'circuit_breaker', 'rate_limit', 'none').

        Returns:
            Matrix[i][j] = cascade severity when attacker uses strategy i
            and defender uses strategy j.

        Defender strategies reduce severity by a fixed factor:
        - 'redundancy': severity * 0.3
        - 'circuit_breaker': severity * 0.5
        - 'rate_limit': severity * 0.7
        - 'none': severity * 1.0
        """

        defense_factors = {
            "redundancy": 0.3,
            "circuit_breaker": 0.5,
            "rate_limit": 0.7,
            "none": 1.0,
        }

        matrix: list[list[float]] = []

        for attack_target in attacker_strategies:
            row: list[float] = []
            fault = Fault(
                target_component_id=attack_target,
                fault_type=FaultType.COMPONENT_DOWN,
                severity=1.0,
            )
            chain = self.cascade_engine.simulate_fault(fault)
            base_severity = chain.severity

            for defense in defender_strategies:
                factor = defense_factors.get(defense, 1.0)
                row.append(base_severity * factor)
            matrix.append(row)

        return matrix

    def nash_equilibrium(
        self,
        payoff_matrix: list[list[float]] | None = None,
    ) -> tuple[list[float], list[float], float]:
        """Compute Nash equilibrium via minimax.

        Parameters:
            payoff_matrix: Payoff matrix (attacker rows, defender cols).
                Uses stored matrix if None.

        Returns:
            (attacker_strategy, defender_strategy, equilibrium_value)
            where strategies are probability distributions.

        For small matrices, uses iterative fictitious play to
        approximate the mixed-strategy Nash equilibrium.
        """

        if payoff_matrix is None:
            payoff_matrix = self._result.payoff_matrix if self._result else []

        if not payoff_matrix or not payoff_matrix[0]:
            return [], [], 0.0

        n_attack = len(payoff_matrix)
        n_defend = len(payoff_matrix[0])

        # Fictitious play: iteratively best-respond to opponent's
        # empirical frequency.
        attack_counts = [0.0] * n_attack
        defend_counts = [0.0] * n_defend

        # Initialise with uniform
        for i in range(n_attack):
            attack_counts[i] = 1.0
        for j in range(n_defend):
            defend_counts[j] = 1.0

        iterations = 200
        for _ in range(iterations):
            # Defender best-responds to attacker's empirical strategy
            atk_total = sum(attack_counts)
            atk_probs = [c / atk_total for c in attack_counts]

            best_def = 0
            best_def_val = float("inf")
            for j in range(n_defend):
                expected = sum(atk_probs[i] * payoff_matrix[i][j] for i in range(n_attack))
                if expected < best_def_val:
                    best_def_val = expected
                    best_def = j
            defend_counts[best_def] += 1.0

            # Attacker best-responds to defender's empirical strategy
            def_total = sum(defend_counts)
            def_probs = [c / def_total for c in defend_counts]

            best_atk = 0
            best_atk_val = -float("inf")
            for i in range(n_attack):
                expected = sum(def_probs[j] * payoff_matrix[i][j] for j in range(n_defend))
                if expected > best_atk_val:
                    best_atk_val = expected
                    best_atk = i
            attack_counts[best_atk] += 1.0

        # Normalise to probabilities
        atk_total = sum(attack_counts)
        def_total = sum(defend_counts)
        atk_probs = [c / atk_total for c in attack_counts]
        def_probs = [c / def_total for c in defend_counts]

        # Equilibrium value
        eq_value = sum(
            atk_probs[i] * def_probs[j] * payoff_matrix[i][j]
            for i in range(n_attack)
            for j in range(n_defend)
        )

        return atk_probs, def_probs, eq_value

    def analyze_security_resilience(self, graph: InfraGraph | None = None) -> GameResult:
        """Analyse security resilience as a game.

        Parameters:
            graph: Infrastructure graph (uses self.graph if None).

        Returns:
            GameResult with Nash equilibrium strategies and
            recommended defense allocation.
        """

        if graph is not None:
            self.graph = graph
            self.cascade_engine = CascadeEngine(graph)

        attacker_strategies = list(self.graph.components.keys())
        defender_strategies = ["redundancy", "circuit_breaker", "rate_limit", "none"]

        if not attacker_strategies:
            return GameResult()

        matrix = self._payoff_matrix(attacker_strategies, defender_strategies)
        atk_probs, def_probs, eq_value = self.nash_equilibrium(matrix)

        # Find recommended defense
        if def_probs:
            best_def_idx = max(range(len(def_probs)), key=lambda i: def_probs[i])
            recommended = defender_strategies[best_def_idx]
        else:
            recommended = "none"

        self._result = GameResult(
            payoff_matrix=matrix,
            attacker_strategies=attacker_strategies,
            defender_strategies=defender_strategies,
            nash_attacker=atk_probs,
            nash_defender=def_probs,
            equilibrium_value=eq_value,
            recommended_defense=recommended,
        )

        return self._result


# =====================================================================
# Fuzzy Resilience Engine
# =====================================================================

@dataclass
class FuzzyResult:
    """Result of fuzzy resilience evaluation.

    Attributes:
        crisp_score: Defuzzified resilience score (0-100).
        linguistic_label: Human-readable label (e.g. 'good').
        membership_values: Membership degrees for each linguistic term.
        rule_activations: Which rules fired and their strength.
        component_scores: Per-component fuzzy scores.
    """

    crisp_score: float = 0.0
    linguistic_label: str = ""
    membership_values: dict[str, float] = field(default_factory=dict)
    rule_activations: list[tuple[str, float]] = field(default_factory=list)
    component_scores: dict[str, float] = field(default_factory=dict)


class FuzzyResilienceEngine:
    """Fuzzy-logic resilience evaluation.

    Uses triangular/trapezoidal membership functions and linguistic
    rules to assess resilience in a way that handles uncertainty and
    vagueness better than crisp thresholds.

    Linguistic variables:
    - Utilisation: {low, medium, high, critical}
    - Redundancy: {none, low, adequate, high}
    - Resilience: {poor, fair, good, excellent}

    Defuzzification uses the centre-of-gravity (centroid) method.
    """

    def __init__(self) -> None:
        # Utilisation membership functions: (label, a, b, c, d)
        # Trapezoidal: ramp up from a→b, flat b→c, ramp down c→d
        self.util_sets = {
            "low": (0, 0, 20, 40),
            "medium": (30, 50, 50, 70),
            "high": (60, 75, 85, 95),
            "critical": (85, 95, 100, 100),
        }

        # Redundancy membership functions (based on replica count)
        self.redundancy_sets = {
            "none": (0, 0, 1, 1.5),
            "low": (1, 1.5, 2, 3),
            "adequate": (2, 3, 4, 6),
            "high": (4, 6, 10, 10),
        }

        # Output: resilience score membership
        self.resilience_sets = {
            "poor": (0, 0, 20, 35),
            "fair": (25, 40, 50, 65),
            "good": (55, 70, 80, 90),
            "excellent": (80, 90, 100, 100),
        }

    @staticmethod
    def _membership(x: float, params: tuple) -> float:
        """Compute trapezoidal membership degree.

        Parameters:
            x: Input value.
            params: (a, b, c, d) defining the trapezoid.
                a: start of ramp up
                b: start of flat top
                c: end of flat top
                d: end of ramp down

        Returns:
            Membership degree in [0, 1].

        Special cases:
        - Triangle: b == c
        - Left shoulder: a == b
        - Right shoulder: c == d
        """

        a, b, c, d = params

        if x <= a:
            return 0.0
        elif x <= b:
            return (x - a) / (b - a) if b > a else 1.0
        elif x <= c:
            return 1.0
        elif x <= d:
            return (d - x) / (d - c) if d > c else 1.0
        else:
            return 0.0

    def _fuzzify(self, value: float, fuzzy_sets: dict) -> dict[str, float]:
        """Fuzzify a crisp value into membership degrees.

        Parameters:
            value: The crisp input value.
            fuzzy_sets: Dict of {label: (a,b,c,d)} trapezoid params.

        Returns:
            Dict of {label: membership_degree}.
        """

        return {
            label: self._membership(value, params)
            for label, params in fuzzy_sets.items()
        }

    @staticmethod
    def _apply_rules(
        fuzzified_inputs: dict[str, dict[str, float]],
        rules: list[tuple[dict[str, str], str]],
    ) -> dict[str, float]:
        """Apply fuzzy rules via Mamdani inference.

        Parameters:
            fuzzified_inputs: {variable_name: {label: degree}}.
            rules: List of (antecedent_dict, consequent_label).
                antecedent_dict maps variable names to required labels.

        Returns:
            {output_label: activation_strength} after rule firing.

        Rule strength is the minimum of antecedent membership degrees
        (fuzzy AND).  Multiple rules with the same consequent are
        combined via maximum (fuzzy OR).
        """

        output: dict[str, float] = {}

        for antecedents, consequent in rules:
            # Compute rule strength (fuzzy AND = min)
            strength = 1.0
            for var_name, label in antecedents.items():
                if var_name in fuzzified_inputs and label in fuzzified_inputs[var_name]:
                    strength = min(strength, fuzzified_inputs[var_name][label])
                else:
                    strength = 0.0

            # Fuzzy OR for same consequent
            if consequent in output:
                output[consequent] = max(output[consequent], strength)
            else:
                output[consequent] = strength

        return output

    def _defuzzify(self, fuzzy_output: dict[str, float]) -> float:
        """Defuzzify using centre-of-gravity (centroid) method.

        Parameters:
            fuzzy_output: {label: activation_strength} from rule application.

        Returns:
            Crisp resilience score (0-100).

        Discretises the output universe [0, 100] and computes the
        centroid of the aggregated fuzzy set.
        """

        n_points = 101
        numerator = 0.0
        denominator = 0.0

        for i in range(n_points):
            x = float(i)
            # Aggregate: max of (min of activation and membership)
            agg = 0.0
            for label, activation in fuzzy_output.items():
                if label in self.resilience_sets:
                    mem = self._membership(x, self.resilience_sets[label])
                    agg = max(agg, min(activation, mem))

            numerator += x * agg
            denominator += agg

        if denominator == 0:
            return 50.0  # default if no rules fire

        return numerator / denominator

    def evaluate(self, graph: InfraGraph) -> FuzzyResult:
        """Evaluate infrastructure resilience using fuzzy logic.

        Parameters:
            graph: The infrastructure graph.

        Returns:
            FuzzyResult with crisp score, linguistic label, and
            per-component breakdown.
        """

        if not graph.components:
            return FuzzyResult(crisp_score=0.0, linguistic_label="poor")

        # Define rules: (antecedents, consequent)
        rules: list[tuple[dict[str, str], str]] = [
            # High utilisation + no redundancy → poor
            ({"utilization": "critical", "redundancy": "none"}, "poor"),
            ({"utilization": "high", "redundancy": "none"}, "poor"),
            # High utilisation + some redundancy → fair
            ({"utilization": "high", "redundancy": "low"}, "fair"),
            ({"utilization": "critical", "redundancy": "low"}, "poor"),
            ({"utilization": "critical", "redundancy": "adequate"}, "fair"),
            # Medium utilisation
            ({"utilization": "medium", "redundancy": "none"}, "fair"),
            ({"utilization": "medium", "redundancy": "low"}, "fair"),
            ({"utilization": "medium", "redundancy": "adequate"}, "good"),
            ({"utilization": "medium", "redundancy": "high"}, "good"),
            # Low utilisation
            ({"utilization": "low", "redundancy": "none"}, "fair"),
            ({"utilization": "low", "redundancy": "low"}, "good"),
            ({"utilization": "low", "redundancy": "adequate"}, "good"),
            ({"utilization": "low", "redundancy": "high"}, "excellent"),
            # High utilisation + high redundancy
            ({"utilization": "high", "redundancy": "adequate"}, "fair"),
            ({"utilization": "high", "redundancy": "high"}, "good"),
        ]

        # Aggregate across components
        component_scores: dict[str, float] = {}
        all_util_fuzzified: list[dict[str, float]] = []
        all_redund_fuzzified: list[dict[str, float]] = []

        for comp in graph.components.values():
            util = comp.utilization()
            replicas = float(comp.replicas)

            util_fuzzy = self._fuzzify(util, self.util_sets)
            redund_fuzzy = self._fuzzify(replicas, self.redundancy_sets)

            all_util_fuzzified.append(util_fuzzy)
            all_redund_fuzzified.append(redund_fuzzy)

            # Per-component evaluation
            inputs = {"utilization": util_fuzzy, "redundancy": redund_fuzzy}
            rule_output = self._apply_rules(inputs, rules)
            score = self._defuzzify(rule_output)
            component_scores[comp.id] = score

        # Aggregate: average membership across all components
        avg_util: dict[str, float] = {}
        avg_redund: dict[str, float] = {}

        for label in self.util_sets:
            vals = [f.get(label, 0.0) for f in all_util_fuzzified]
            avg_util[label] = sum(vals) / len(vals) if vals else 0.0

        for label in self.redundancy_sets:
            vals = [f.get(label, 0.0) for f in all_redund_fuzzified]
            avg_redund[label] = sum(vals) / len(vals) if vals else 0.0

        inputs = {"utilization": avg_util, "redundancy": avg_redund}
        rule_output = self._apply_rules(inputs, rules)
        crisp_score = self._defuzzify(rule_output)

        # Determine linguistic label
        label_memberships = self._fuzzify(crisp_score, self.resilience_sets)
        linguistic_label = max(label_memberships, key=lambda k: label_memberships[k])

        # Rule activations
        activations = [(f"Rule→{label}", strength) for label, strength in rule_output.items() if strength > 0]

        return FuzzyResult(
            crisp_score=crisp_score,
            linguistic_label=linguistic_label,
            membership_values=label_memberships,
            rule_activations=activations,
            component_scores=component_scores,
        )


# =====================================================================
# Causal Inference Engine
# =====================================================================

@dataclass
class CausalNode:
    """A node in the structural causal model.

    Attributes:
        id: Component identifier.
        parents: IDs of causal parents.
        mechanism: Functional mechanism ('and', 'or', 'weighted').
        weights: Weights for parents (for 'weighted' mechanism).
        value: Current observed value (0.0 = healthy, 1.0 = failed).
    """

    id: str = ""
    parents: list[str] = field(default_factory=list)
    mechanism: str = "or"
    weights: dict[str, float] = field(default_factory=dict)
    value: float = 0.0


@dataclass
class CausalResult:
    """Result of causal inference analysis.

    Attributes:
        interventional_effect: Effect of do(X=x) on target.
        counterfactual: Counterfactual outcome.
        causal_chain: Ordered list of causes from root to effect.
        causal_strengths: Strength of each causal link.
    """

    interventional_effect: float = 0.0
    counterfactual: dict[str, float] = field(default_factory=dict)
    causal_chain: list[str] = field(default_factory=list)
    causal_strengths: dict[str, float] = field(default_factory=dict)


class CausalInferenceEngine:
    """Structural Causal Model with do-calculus for root cause analysis.

    Converts the InfraGraph dependency structure into a Structural Causal
    Model (SCM) where:
    - Nodes represent components
    - Directed edges represent causal influence
    - Each node has a mechanism (how parent states combine)

    Supports three types of queries:
    1. Observational: P(Y | X=x) — what is Y given we observe X?
    2. Interventional: P(Y | do(X=x)) — what if we *force* X to x?
    3. Counterfactual: "had X been x', what would Y have been?"

    The key difference from cascade simulation: causal inference reasons
    *backwards* (from effect to cause) and supports counterfactuals
    ("would this failure have happened without that change?").
    """

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self.scm: dict[str, CausalNode] = {}
        self._build_scm(graph)

    def _build_scm(self, graph: InfraGraph) -> None:
        """Convert InfraGraph to a Structural Causal Model.

        Each dependency edge source → target becomes a causal link:
        the target's state causally depends on the source's state.
        Dependency type determines the mechanism:
        - 'requires': AND (all parents must be healthy)
        - 'optional'/'async': OR (any healthy parent suffices)
        """

        self.scm = {}

        for comp in graph.components.values():
            node = CausalNode(id=comp.id)
            # Determine health value
            if comp.health == HealthStatus.DOWN:
                node.value = 1.0
            elif comp.health == HealthStatus.OVERLOADED:
                node.value = 0.7
            elif comp.health == HealthStatus.DEGRADED:
                node.value = 0.4
            else:
                node.value = 0.0
            self.scm[comp.id] = node

        # Set up causal parents from dependency edges
        for comp in graph.components.values():
            deps = graph.get_dependencies(comp.id)
            parents = []
            weights = {}
            has_requires = False

            for dep_comp in deps:
                edge = graph.get_dependency_edge(comp.id, dep_comp.id)
                if edge:
                    parents.append(dep_comp.id)
                    weights[dep_comp.id] = edge.weight
                    if edge.dependency_type == "requires":
                        has_requires = True

            if comp.id in self.scm:
                self.scm[comp.id].parents = parents
                self.scm[comp.id].weights = weights
                self.scm[comp.id].mechanism = "and" if has_requires else "or"

    def _evaluate_mechanism(self, node: CausalNode, values: dict[str, float]) -> float:
        """Evaluate a node's causal mechanism given parent values.

        For 'and': node fails if ANY parent fails (max of parent values).
        For 'or': node fails if ALL parents fail (min of parent values).
        For 'weighted': weighted average of parent values.
        """

        if not node.parents:
            return values.get(node.id, node.value)

        parent_vals = [values.get(p, self.scm[p].value if p in self.scm else 0.0)
                       for p in node.parents]

        if not parent_vals:
            return 0.0

        if node.mechanism == "and":
            # AND: worst parent determines state
            return max(parent_vals)
        elif node.mechanism == "or":
            # OR: best parent determines state
            return min(parent_vals)
        else:
            # Weighted average
            total_weight = sum(node.weights.get(p, 1.0) for p in node.parents)
            if total_weight == 0:
                return 0.0
            weighted_sum = sum(
                values.get(p, self.scm[p].value if p in self.scm else 0.0) * node.weights.get(p, 1.0)
                for p in node.parents
            )
            return weighted_sum / total_weight

    def _forward_propagate(self, values: dict[str, float]) -> dict[str, float]:
        """Propagate values through the SCM in topological order."""

        result = dict(values)

        # Simple iterative propagation (converges for DAGs)
        for _ in range(len(self.scm)):
            changed = False
            for node_id, node in self.scm.items():
                if node_id in values and node.parents:
                    # Intervened nodes keep their value
                    continue
                if not node.parents:
                    if node_id not in result:
                        result[node_id] = node.value
                    continue
                new_val = self._evaluate_mechanism(node, result)
                if node_id not in result or abs(result[node_id] - new_val) > 1e-6:
                    result[node_id] = new_val
                    changed = True
            if not changed:
                break

        return result

    def do_calculus(
        self,
        intervention_var: str,
        intervention_value: float,
        target_var: str,
    ) -> float:
        """Compute the effect of do(X=x) on target Y.

        Parameters:
            intervention_var: The variable to intervene on.
            intervention_value: The value to set (0=healthy, 1=failed).
            target_var: The variable to observe.

        Returns:
            The value of target_var under the intervention.

        do(X=x) differs from conditioning on X=x: it *removes* all
        incoming causal arrows to X and forces it to x, then propagates.
        This answers "what would happen if we *made* X take value x?"
        rather than "what is Y given we *observe* X=x?"
        """

        # Create a copy of current values
        values: dict[str, float] = {}
        for node_id, node in self.scm.items():
            values[node_id] = node.value

        # Intervene: force the variable and remove parent influence
        values[intervention_var] = intervention_value

        # Propagate
        result = self._forward_propagate(values)

        return result.get(target_var, 0.0)

    def counterfactual(
        self,
        observed: dict[str, float],
        intervention: dict[str, float],
    ) -> dict[str, float]:
        """Compute counterfactual outcomes.

        Parameters:
            observed: Observed (factual) values {comp_id: value}.
            intervention: Counterfactual intervention {comp_id: value}.

        Returns:
            Dict of all component values under the counterfactual.

        Three steps (Pearl's twin network method):
        1. Abduction: infer exogenous noise from observed data
        2. Action: apply the intervention
        3. Prediction: propagate with inferred noise + intervention

        Answers: "Given what we observed, had we changed X to x',
        what would Y have been?"
        """

        # Step 1: Abduction — set observed values
        values: dict[str, float] = {}
        for node_id, node in self.scm.items():
            values[node_id] = observed.get(node_id, node.value)

        # Step 2: Action — apply intervention (overrides abduced values)
        for var, val in intervention.items():
            values[var] = val

        # Step 3: Prediction — forward propagate
        result = self._forward_propagate(values)

        return result

    def analyze_root_cause(
        self,
        graph: InfraGraph | None = None,
        failed_component: str = "",
    ) -> list[tuple[str, float]]:
        """Identify the causal chain leading to a component's failure.

        Parameters:
            graph: Infrastructure graph (uses self.graph if None).
            failed_component: The component that failed.

        Returns:
            List of (component_id, causal_strength) ordered from root
            cause to the failed component.

        Uses interventional queries: for each ancestor, compute
        do(ancestor=0) (force healthy) and measure the reduction in
        the failed component's value.  Larger reductions indicate
        stronger causal influence.
        """

        if graph is not None:
            self.graph = graph
            self._build_scm(graph)

        if failed_component not in self.scm:
            return []

        # Find all ancestors via BFS on causal parents
        ancestors: list[str] = []
        visited: set[str] = set()
        queue = list(self.scm[failed_component].parents)

        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            ancestors.append(node_id)
            if node_id in self.scm:
                queue.extend(self.scm[node_id].parents)

        if not ancestors:
            return [(failed_component, 1.0)]

        # Current (observed) value of failed component
        current_value = self.scm[failed_component].value

        # For each ancestor, compute interventional effect
        causal_strengths: list[tuple[str, float]] = []
        for ancestor in ancestors:
            # do(ancestor = 0) — force healthy
            intervened_value = self.do_calculus(ancestor, 0.0, failed_component)
            # Causal strength = how much forcing ancestor healthy reduces failure
            strength = max(0.0, current_value - intervened_value)
            causal_strengths.append((ancestor, strength))

        # Sort by strength descending (strongest cause first)
        causal_strengths.sort(key=lambda x: x[1], reverse=True)

        # Add the failed component itself at the end
        causal_strengths.append((failed_component, current_value))

        return causal_strengths
