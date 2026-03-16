"""Time-Series, Ensemble, and Swarm Intelligence Engines.

Three complementary approaches for *predicting* failures and
*optimising* fault-injection scenarios:

1. **ARIMAPredictor** — AutoRegressive Integrated Moving Average for
   time-series forecasting of component metrics (CPU, memory, latency).
   Predicts when metrics will breach thresholds, enabling proactive
   failure avoidance.
   *Difference from RNN (rnn_predictor.py)*: ARIMA is a classical
   statistical model with interpretable (p, d, q) parameters and no
   training data requirements beyond the target series; RNN learns
   non-linear temporal patterns but needs substantial training data.

2. **BoostingPredictor** — AdaBoost ensemble of decision stumps for
   binary failure classification.  Each round trains a weak learner
   on re-weighted data, focusing on previously misclassified samples.
   *Difference from RandomForest (optimization_engines.py)*: RF trains
   trees independently via bagging; AdaBoost trains *sequentially*,
   each learner correcting the previous one's errors, producing a
   *weighted* ensemble that excels at hard-to-classify boundary cases.

3. **ParticleSwarmOptimizer** — PSO for discovering worst-case failure
   scenarios.  A swarm of particles explores the fault-configuration
   space, sharing information about the best positions found.
   *Difference from GA (ga_scenario_optimizer.py)*: GA uses crossover
   and mutation on discrete chromosomes; PSO uses continuous velocity
   updates with personal and global best memory, often converging
   faster in continuous spaces.

All implementations use **standard library only** (math, random, statistics).
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field

from faultray.model.graph import InfraGraph
from faultray.simulator.cascade import CascadeChain, CascadeEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario


# =====================================================================
# ARIMA Predictor
# =====================================================================

@dataclass
class FailurePrediction:
    """Prediction of when a component metric will breach a threshold.

    Attributes:
        component_id: The component being monitored.
        metric_name: Name of the metric (e.g. 'cpu_percent').
        current_value: Most recent observed value.
        threshold: The failure threshold.
        predicted_values: Forecasted future values.
        steps_to_breach: Number of steps until threshold is breached
            (-1 if never breached within prediction horizon).
        confidence: Rough confidence estimate (0-1).
    """

    component_id: str = ""
    metric_name: str = ""
    current_value: float = 0.0
    threshold: float = 0.0
    predicted_values: list[float] = field(default_factory=list)
    steps_to_breach: int = -1
    confidence: float = 0.0


class ARIMAPredictor:
    """ARIMA(p, d, q) time-series predictor for infrastructure metrics.

    ARIMA combines three components:
    - AR (AutoRegressive): current value depends on p previous values
    - I (Integrated): d-th order differencing to make series stationary
    - MA (Moving Average): current value depends on q previous forecast errors

    The simplified implementation uses:
    - Least-squares estimation for AR coefficients
    - Residual-based MA coefficient estimation
    - Iterative differencing/integration
    """

    def __init__(self, p: int = 3, d: int = 1, q: int = 2) -> None:
        self.p = p
        self.d = d
        self.q = q
        self.ar_coeffs: list[float] = []
        self.ma_coeffs: list[float] = []
        self.intercept: float = 0.0
        self._fitted = False
        self._original_series: list[float] = []
        self._diff_series: list[float] = []
        self._residuals: list[float] = []

    @staticmethod
    def _difference(series: list[float], d: int = 1) -> list[float]:
        """Apply d-th order differencing to make a series stationary.

        First difference: y'[t] = y[t] - y[t-1]
        Second difference: y''[t] = y'[t] - y'[t-1]
        And so on for higher orders.
        """

        result = list(series)
        for _ in range(d):
            if len(result) < 2:
                break
            result = [result[i] - result[i - 1] for i in range(1, len(result))]
        return result

    def _autoregressive(self, series: list[float], p: int = 3) -> list[float]:
        """Estimate AR(p) coefficients via least-squares.

        Solves the Yule-Walker-like system using a simplified
        approach: coefficients are estimated from autocorrelation.

        Parameters:
            series: The (differenced) time series.
            p: AR order.

        Returns:
            List of p AR coefficients.
        """

        if len(series) <= p:
            return [0.0] * p

        n = len(series)
        mean = sum(series) / n

        # Compute autocorrelations
        var = sum((x - mean) ** 2 for x in series) / n
        if var == 0:
            return [0.0] * p

        autocorr = []
        for lag in range(p + 1):
            c = sum((series[i] - mean) * (series[i - lag] - mean)
                    for i in range(lag, n)) / n
            autocorr.append(c / var)

        # Levinson-Durbin algorithm for AR coefficients
        coeffs = [0.0] * p
        if p == 0:
            return coeffs

        # Order 1
        coeffs[0] = autocorr[1]
        prev = [autocorr[1]]

        for order in range(2, p + 1):
            # Compute reflection coefficient
            num = autocorr[order] - sum(
                prev[j] * autocorr[order - 1 - j] for j in range(len(prev))
            )
            denom = 1.0 - sum(
                prev[j] * autocorr[j + 1] for j in range(len(prev))
            )
            if abs(denom) < 1e-10:
                break
            k = num / denom

            # Update coefficients
            new_coeffs = []
            for j in range(len(prev)):
                new_coeffs.append(prev[j] - k * prev[len(prev) - 1 - j])
            new_coeffs.append(k)
            prev = new_coeffs

        for i in range(min(len(prev), p)):
            coeffs[i] = prev[i]

        return coeffs

    def _moving_average(self, residuals: list[float], q: int = 2) -> list[float]:
        """Estimate MA(q) coefficients from residual autocorrelation.

        Parameters:
            residuals: The AR model residuals.
            q: MA order.

        Returns:
            List of q MA coefficients.
        """

        if len(residuals) <= q or q == 0:
            return [0.0] * q

        n = len(residuals)
        mean = sum(residuals) / n
        var = sum((r - mean) ** 2 for r in residuals) / n
        if var == 0:
            return [0.0] * q

        ma_coeffs = []
        for lag in range(1, q + 1):
            c = sum((residuals[i] - mean) * (residuals[i - lag] - mean)
                    for i in range(lag, n)) / n
            ma_coeffs.append(c / var)

        return ma_coeffs

    def fit(self, time_series: list[float]) -> None:
        """Fit the ARIMA model to a time series.

        Parameters:
            time_series: Observed metric values in chronological order.

        Steps:
        1. Apply d-th order differencing
        2. Estimate AR(p) coefficients
        3. Compute residuals
        4. Estimate MA(q) coefficients from residuals
        """

        if len(time_series) < self.p + self.d + 2:
            self.ar_coeffs = [0.0] * self.p
            self.ma_coeffs = [0.0] * self.q
            self._fitted = True
            self._original_series = list(time_series)
            return

        self._original_series = list(time_series)

        # Step 1: Differencing
        self._diff_series = self._difference(time_series, self.d)

        # Step 2: AR coefficients
        self.ar_coeffs = self._autoregressive(self._diff_series, self.p)

        # Step 3: Compute residuals
        self._residuals = []
        mean_diff = sum(self._diff_series) / len(self._diff_series) if self._diff_series else 0.0
        self.intercept = mean_diff

        for t in range(self.p, len(self._diff_series)):
            predicted = self.intercept
            for j in range(self.p):
                predicted += self.ar_coeffs[j] * self._diff_series[t - 1 - j]
            self._residuals.append(self._diff_series[t] - predicted)

        # Step 4: MA coefficients
        self.ma_coeffs = self._moving_average(self._residuals, self.q)

        self._fitted = True

    def predict(self, steps: int = 10) -> list[float]:
        """Forecast future values.

        Parameters:
            steps: Number of future time steps to predict.

        Returns:
            List of predicted values (in original scale, not differenced).

        The method predicts in the differenced domain, then integrates
        back to the original scale.
        """

        if not self._fitted or not self._original_series:
            return [0.0] * steps

        # Extend the differenced series
        diff_ext = list(self._diff_series)
        resid_ext = list(self._residuals) if self._residuals else [0.0]

        for _ in range(steps):
            val = self.intercept

            # AR component
            for j in range(self.p):
                idx = len(diff_ext) - 1 - j
                if 0 <= idx < len(diff_ext):
                    val += self.ar_coeffs[j] * diff_ext[idx]

            # MA component
            for j in range(self.q):
                idx = len(resid_ext) - 1 - j
                if 0 <= idx < len(resid_ext):
                    val += self.ma_coeffs[j] * resid_ext[idx]

            diff_ext.append(val)
            resid_ext.append(0.0)  # future residuals unknown → 0

        predicted_diff = diff_ext[len(self._diff_series):]

        # Integrate back (reverse differencing)
        result = list(predicted_diff)
        for _ in range(self.d):
            # Need last value from original at each integration level
            last_vals = list(self._original_series)
            for d_step in range(self.d - 1):
                last_vals = self._difference(last_vals, 1)
            last_val = last_vals[-1] if last_vals else 0.0
            integrated = []
            prev = last_val
            for v in result:
                prev = prev + v
                integrated.append(prev)
            result = integrated

        return result

    def predict_failure(
        self,
        component_metrics: list[float],
        threshold: float,
        component_id: str = "",
        metric_name: str = "metric",
        steps: int = 20,
    ) -> FailurePrediction:
        """Predict when a component metric will breach a threshold.

        Parameters:
            component_metrics: Historical metric values.
            threshold: The value at which failure occurs.
            component_id: Identifier of the component.
            metric_name: Name of the metric.
            steps: Prediction horizon.

        Returns:
            FailurePrediction with time-to-breach and forecasted values.
        """

        self.fit(component_metrics)
        predicted = self.predict(steps)

        steps_to_breach = -1
        for i, val in enumerate(predicted):
            if val >= threshold:
                steps_to_breach = i + 1
                break

        # Rough confidence based on fit quality
        confidence = 0.5
        if self._residuals:
            residual_std = (sum(r ** 2 for r in self._residuals) / len(self._residuals)) ** 0.5
            series_std = statistics.pstdev(component_metrics) if len(component_metrics) > 1 else 1.0
            if series_std > 0:
                r_squared = max(0.0, 1.0 - (residual_std / series_std) ** 2)
                confidence = min(0.95, r_squared)

        return FailurePrediction(
            component_id=component_id,
            metric_name=metric_name,
            current_value=component_metrics[-1] if component_metrics else 0.0,
            threshold=threshold,
            predicted_values=predicted,
            steps_to_breach=steps_to_breach,
            confidence=confidence,
        )


# =====================================================================
# Boosting Predictor (AdaBoost)
# =====================================================================

@dataclass
class WeakLearner:
    """A decision stump — single-split binary classifier.

    Attributes:
        feature_idx: Index of the feature to split on.
        threshold: Split threshold value.
        polarity: +1 or -1 (direction of the split).
        alpha: Weight of this learner in the ensemble.
    """

    feature_idx: int = 0
    threshold: float = 0.0
    polarity: int = 1
    alpha: float = 0.0

    def predict_one(self, x: list[float]) -> float:
        """Classify a single sample. Returns +1 or -1."""
        if self.polarity * x[self.feature_idx] < self.polarity * self.threshold:
            return 1.0
        return -1.0


class BoostingPredictor:
    """AdaBoost ensemble of decision stumps for failure prediction.

    AdaBoost iteratively:
    1. Trains a weak learner (decision stump) on weighted data
    2. Computes its weighted error
    3. Calculates learner weight alpha = 0.5 * ln((1-e)/e)
    4. Re-weights samples: increase weight of misclassified samples

    The final prediction is the sign of the weighted sum of all
    weak learner predictions.

    This is well-suited for binary failure classification where the
    failure boundary is complex and non-linear.
    """

    def __init__(self) -> None:
        self.learners: list[WeakLearner] = []
        self._trained = False

    def _train_stump(
        self,
        features: list[list[float]],
        labels: list[float],
        weights: list[float],
    ) -> WeakLearner:
        """Train a single decision stump (best feature + threshold).

        Finds the feature and threshold that minimises weighted
        classification error.
        """

        n = len(features)
        if n == 0:
            return WeakLearner()

        n_features = len(features[0])
        best_stump = WeakLearner()
        best_error = float("inf")

        for feat_idx in range(n_features):
            values = sorted(set(features[i][feat_idx] for i in range(n)))

            # Try thresholds between consecutive unique values
            thresholds = []
            for i in range(len(values) - 1):
                thresholds.append((values[i] + values[i + 1]) / 2.0)
            if not thresholds:
                thresholds = [values[0] - 0.5, values[0] + 0.5] if values else [0.0]

            for threshold in thresholds:
                for polarity in [1, -1]:
                    error = 0.0
                    for i in range(n):
                        if polarity * features[i][feat_idx] < polarity * threshold:
                            pred = 1.0
                        else:
                            pred = -1.0
                        if pred != labels[i]:
                            error += weights[i]

                    if error < best_error:
                        best_error = error
                        best_stump = WeakLearner(
                            feature_idx=feat_idx,
                            threshold=threshold,
                            polarity=polarity,
                        )

        return best_stump

    def train(
        self,
        features: list[list[float]],
        labels: list[float],
        n_estimators: int = 50,
    ) -> None:
        """Train the AdaBoost ensemble.

        Parameters:
            features: Training feature vectors.
            labels: Binary labels (+1 for failure, -1 for normal).
            n_estimators: Number of boosting rounds.

        Each round:
        1. Train decision stump on weighted data
        2. Compute weighted error
        3. Calculate alpha = 0.5 * ln((1-error)/error)
        4. Update sample weights: w_i *= exp(-alpha * y_i * h(x_i))
        5. Normalise weights
        """

        n = len(features)
        if n == 0:
            return

        # Ensure labels are +1/-1
        labels = [1.0 if y > 0 else -1.0 for y in labels]

        # Initialise uniform weights
        weights = [1.0 / n] * n
        self.learners = []

        for _ in range(n_estimators):
            stump = self._train_stump(features, labels, weights)

            # Compute weighted error
            error = 0.0
            predictions = []
            for i in range(n):
                pred = stump.predict_one(features[i])
                predictions.append(pred)
                if pred != labels[i]:
                    error += weights[i]

            # Clamp error to avoid log(0) or negative alpha
            error = max(1e-10, min(1.0 - 1e-10, error))

            # Learner weight
            alpha = 0.5 * math.log((1.0 - error) / error)
            stump.alpha = alpha
            self.learners.append(stump)

            # Update weights
            for i in range(n):
                weights[i] *= math.exp(-alpha * labels[i] * predictions[i])

            # Normalise
            w_sum = sum(weights)
            if w_sum > 0:
                weights = [w / w_sum for w in weights]

        self._trained = True

    def predict(self, features: list[list[float]]) -> list[float]:
        """Predict failure probability for each sample.

        Parameters:
            features: Feature vectors to classify.

        Returns:
            List of scores in [-1, 1] range. Positive values indicate
            predicted failure; magnitude indicates confidence.
            The score is the normalised weighted vote of all learners.
        """

        if not self.learners:
            return [0.0] * len(features)

        total_alpha = sum(abs(l.alpha) for l in self.learners)
        if total_alpha == 0:
            return [0.0] * len(features)

        results = []
        for x in features:
            score = sum(l.alpha * l.predict_one(x) for l in self.learners)
            # Normalise to [-1, 1]
            results.append(max(-1.0, min(1.0, score / total_alpha)))
        return results


# =====================================================================
# Particle Swarm Optimizer (PSO)
# =====================================================================

@dataclass
class Particle:
    """A single particle in the swarm.

    Attributes:
        position: Current position in the search space (fault severities).
        velocity: Current velocity vector.
        best_position: Personal best position found.
        best_fitness: Fitness at personal best.
    """

    position: list[float] = field(default_factory=list)
    velocity: list[float] = field(default_factory=list)
    best_position: list[float] = field(default_factory=list)
    best_fitness: float = 0.0


@dataclass
class PSOResult:
    """Result of PSO optimisation.

    Attributes:
        best_position: Global best position (fault severities per component).
        best_fitness: Cascade severity at global best.
        best_scenario: The Scenario object corresponding to global best.
        convergence_history: Per-iteration global best fitness.
        iterations_run: Number of iterations completed.
    """

    best_position: list[float] = field(default_factory=list)
    best_fitness: float = 0.0
    best_scenario: Scenario | None = None
    convergence_history: list[float] = field(default_factory=list)
    iterations_run: int = 0


class ParticleSwarmOptimizer:
    """PSO for discovering worst-case fault injection scenarios.

    Each particle represents a fault-configuration vector where
    dimension i is the severity [0, 1] of faulting component i.
    The fitness function uses CascadeEngine to evaluate cascade
    severity.

    PSO update rule:
        v = w*v + c1*r1*(pbest - x) + c2*r2*(gbest - x)
        x = x + v

    Where:
        w   = inertia weight (decays over iterations)
        c1  = cognitive coefficient (personal best attraction)
        c2  = social coefficient (global best attraction)
        r1, r2 = random values in [0, 1]
    """

    def __init__(
        self,
        graph: InfraGraph,
        n_particles: int = 30,
        max_iter: int = 100,
        w: float = 0.9,
        c1: float = 2.0,
        c2: float = 2.0,
        severity_threshold: float = 0.3,
    ) -> None:
        self.graph = graph
        self.n_particles = n_particles
        self.max_iter = max_iter
        self.w_start = w
        self.w_end = 0.4
        self.c1 = c1
        self.c2 = c2
        self.severity_threshold = severity_threshold

        self.component_ids = list(graph.components.keys())
        self.dim = len(self.component_ids)
        self.cascade_engine = CascadeEngine(graph)

        self.particles: list[Particle] = []
        self.global_best_position: list[float] = []
        self.global_best_fitness: float = 0.0

    def _fitness(self, position: list[float]) -> float:
        """Evaluate a position by simulating its cascade severity.

        Components with severity > severity_threshold are faulted.
        The fitness is the resulting CascadeChain severity (0-10).
        """

        faults = []
        for i, comp_id in enumerate(self.component_ids):
            if position[i] > self.severity_threshold:
                faults.append(Fault(
                    target_component_id=comp_id,
                    fault_type=FaultType.COMPONENT_DOWN,
                    severity=position[i],
                ))

        if not faults:
            return 0.0

        # Simulate the first fault and accumulate severity
        total_severity = 0.0
        for fault in faults:
            chain = self.cascade_engine.simulate_fault(fault)
            total_severity += chain.severity

        return total_severity

    def _position_to_scenario(self, position: list[float]) -> Scenario:
        """Convert a position vector to a Scenario object."""
        faults = []
        for i, comp_id in enumerate(self.component_ids):
            if position[i] > self.severity_threshold:
                faults.append(Fault(
                    target_component_id=comp_id,
                    fault_type=FaultType.COMPONENT_DOWN,
                    severity=position[i],
                ))

        return Scenario(
            id="pso-optimal",
            name="PSO Worst-Case Scenario",
            description=(
                f"Scenario discovered by PSO with fitness {self.global_best_fitness:.2f}. "
                f"Faults {len(faults)} of {self.dim} components."
            ),
            faults=faults,
        )

    def optimize(self) -> PSOResult:
        """Run PSO to find the worst-case failure scenario.

        Returns:
            PSOResult with the best scenario, fitness, and
            convergence history.

        The swarm explores the [0, 1]^dim space where each dimension
        controls the severity of faulting a component.  Inertia weight
        decays linearly from w_start to w_end over iterations.
        """

        if self.dim == 0:
            return PSOResult()

        # Initialise particles
        self.particles = []
        for _ in range(self.n_particles):
            pos = [random.uniform(0, 1) for _ in range(self.dim)]
            vel = [random.uniform(-0.5, 0.5) for _ in range(self.dim)]
            fitness = self._fitness(pos)
            p = Particle(
                position=list(pos),
                velocity=vel,
                best_position=list(pos),
                best_fitness=fitness,
            )
            self.particles.append(p)

            if fitness > self.global_best_fitness:
                self.global_best_fitness = fitness
                self.global_best_position = list(pos)

        if not self.global_best_position:
            self.global_best_position = [0.0] * self.dim

        convergence: list[float] = [self.global_best_fitness]

        for iteration in range(self.max_iter):
            # Linearly decay inertia
            w = self.w_start - (self.w_start - self.w_end) * iteration / max(1, self.max_iter - 1)

            for p in self.particles:
                # Update velocity
                for d in range(self.dim):
                    r1 = random.random()
                    r2 = random.random()
                    cognitive = self.c1 * r1 * (p.best_position[d] - p.position[d])
                    social = self.c2 * r2 * (self.global_best_position[d] - p.position[d])
                    p.velocity[d] = w * p.velocity[d] + cognitive + social

                    # Clamp velocity
                    p.velocity[d] = max(-1.0, min(1.0, p.velocity[d]))

                # Update position
                for d in range(self.dim):
                    p.position[d] += p.velocity[d]
                    # Clamp to [0, 1]
                    p.position[d] = max(0.0, min(1.0, p.position[d]))

                # Evaluate fitness
                fitness = self._fitness(p.position)

                # Update personal best
                if fitness > p.best_fitness:
                    p.best_fitness = fitness
                    p.best_position = list(p.position)

                # Update global best
                if fitness > self.global_best_fitness:
                    self.global_best_fitness = fitness
                    self.global_best_position = list(p.position)

            convergence.append(self.global_best_fitness)

        scenario = self._position_to_scenario(self.global_best_position)

        return PSOResult(
            best_position=list(self.global_best_position),
            best_fitness=self.global_best_fitness,
            best_scenario=scenario,
            convergence_history=convergence,
            iterations_run=self.max_iter,
        )

    def best_scenario(self) -> Scenario:
        """Return the best scenario found (call optimize() first).

        Returns:
            Scenario corresponding to the global best position.
        """

        return self._position_to_scenario(self.global_best_position)
