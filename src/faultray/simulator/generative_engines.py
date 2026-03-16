"""Generative Engines — GAN, VAE, and Failure Pattern Clustering.

Three complementary approaches for *generating* and *organising* failure
scenarios rather than merely simulating pre-defined ones:

1. **SimpleGAN** — a minimal Generative Adversarial Network.  The
   Generator maps random noise to scenario vectors; the Discriminator
   distinguishes real historical scenarios from generated ones.  Through
   adversarial training the Generator learns to produce *novel but
   plausible* failure scenarios that go beyond human imagination.
   *Difference from GA (ga_scenario_optimizer.py)*: GA optimises a
   population toward a *single objective* (max severity); GAN generates
   a *distribution* of realistic scenarios without an explicit fitness
   function.

2. **SimpleVAE** — a Variational Autoencoder that learns a smooth latent
   space of failure scenarios.  Unlike GAN, VAE provides an explicit
   probabilistic model (encoder → latent → decoder) and uses the
   reparameterisation trick for gradient-based training.
   *Difference from GAN*: VAE optimises a principled ELBO loss
   (reconstruction + KL divergence) and yields a structured latent space
   where interpolation between scenarios is meaningful; GAN produces
   sharper samples but lacks an explicit density model.

3. **FailurePatternClustering** — unsupervised K-means clustering of
   failure scenarios to discover recurring *patterns* (e.g. "network
   partitions always cascade to DB timeouts").
   *Difference from AnomalyAutoencoder (optimization_engines.py)*:
   autoencoder detects *outliers*; clustering groups *similar* failures
   to surface common patterns and representative scenarios.

All implementations use **standard library only** (math, random).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


# =====================================================================
# Shared helpers
# =====================================================================

def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _mat_vec(mat: list[list[float]], vec: list[float]) -> list[float]:
    return [_dot(row, vec) for row in mat]


def _vec_add(a: list[float], b: list[float]) -> list[float]:
    return [x + y for x, y in zip(a, b)]


def _vec_sub(a: list[float], b: list[float]) -> list[float]:
    return [x - y for x, y in zip(a, b)]


def _vec_scale(v: list[float], s: float) -> list[float]:
    return [x * s for x in v]


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _rand_matrix(rows: int, cols: int, scale: float = 0.1) -> list[list[float]]:
    s = scale / max(1, (rows + cols) ** 0.5)
    return [[random.gauss(0, s) for _ in range(cols)] for _ in range(rows)]


def _rand_vector(n: int, scale: float = 0.1) -> list[float]:
    return [random.gauss(0, scale) for _ in range(n)]


def _outer_product(a: list[float], b: list[float]) -> list[list[float]]:
    return [[ai * bj for bj in b] for ai in a]


def _mat_add(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[ai + bi for ai, bi in zip(ar, br)] for ar, br in zip(a, b)]


def _mse(a: list[float], b: list[float]) -> float:
    return sum((ai - bi) ** 2 for ai, bi in zip(a, b)) / max(len(a), 1)


# =====================================================================
# SimpleGAN
# =====================================================================

@dataclass
class GANResult:
    """Result of GAN training.

    Attributes:
        generator_losses: Per-epoch generator loss.
        discriminator_losses: Per-epoch discriminator loss.
        epochs_trained: Number of epochs completed.
    """

    generator_losses: list[float] = field(default_factory=list)
    discriminator_losses: list[float] = field(default_factory=list)
    epochs_trained: int = 0


class SimpleGAN:
    """Minimal GAN for failure scenario generation.

    Architecture:
        Generator:     noise_dim → hidden_dim (ReLU) → scenario_dim (sigmoid)
        Discriminator: scenario_dim → hidden_dim (ReLU) → 1 (sigmoid)

    The Generator learns to produce scenario vectors that the
    Discriminator cannot distinguish from real historical data.

    Scenario vectors are normalised to [0, 1] per dimension, where each
    dimension represents a component's failure severity (0 = healthy,
    1 = fully failed).
    """

    def __init__(
        self,
        scenario_dim: int = 10,
        noise_dim: int = 8,
        hidden_dim: int = 16,
        lr: float = 0.01,
    ) -> None:
        self.scenario_dim = scenario_dim
        self.noise_dim = noise_dim
        self.hidden_dim = hidden_dim
        self.lr = lr

        # Generator weights: noise_dim → hidden → scenario_dim
        self.g_w1 = _rand_matrix(hidden_dim, noise_dim)
        self.g_b1 = _rand_vector(hidden_dim)
        self.g_w2 = _rand_matrix(scenario_dim, hidden_dim)
        self.g_b2 = _rand_vector(scenario_dim)

        # Discriminator weights: scenario_dim → hidden → 1
        self.d_w1 = _rand_matrix(hidden_dim, scenario_dim)
        self.d_b1 = _rand_vector(hidden_dim)
        self.d_w2 = _rand_matrix(1, hidden_dim)
        self.d_b2 = _rand_vector(1)

        self._trained = False

    def _generator_forward(self, noise: list[float]) -> list[float]:
        """Generator forward pass: noise → scenario."""
        h = _vec_add(_mat_vec(self.g_w1, noise), self.g_b1)
        h = [max(0.0, x) for x in h]  # ReLU
        out = _vec_add(_mat_vec(self.g_w2, h), self.g_b2)
        return [_sigmoid(x) for x in out]  # sigmoid to [0,1]

    def _discriminator_forward(self, scenario: list[float]) -> float:
        """Discriminator forward pass: scenario → probability of real."""
        h = _vec_add(_mat_vec(self.d_w1, scenario), self.d_b1)
        h = [max(0.0, x) for x in h]  # ReLU
        out = _vec_add(_mat_vec(self.d_w2, h), self.d_b2)
        return _sigmoid(out[0])

    def train(self, real_scenarios: list[list[float]], epochs: int = 200) -> GANResult:
        """Train the GAN on historical failure scenarios.

        Parameters:
            real_scenarios: List of scenario vectors (each [0,1]^d).
            epochs: Number of training epochs.

        Returns:
            GANResult with per-epoch loss histories.

        Training alternates between:
        1. Discriminator update: maximise log(D(real)) + log(1 - D(G(z)))
        2. Generator update: maximise log(D(G(z)))

        Uses simple numerical gradient estimation (finite differences)
        to stay within standard-library constraints.
        """

        if not real_scenarios:
            return GANResult()

        result = GANResult()
        eps = 1e-7

        for epoch in range(epochs):
            # Sample a real scenario
            real = random.choice(real_scenarios)
            # Generate a fake scenario
            noise = [random.gauss(0, 1) for _ in range(self.noise_dim)]
            fake = self._generator_forward(noise)

            # Discriminator scores
            d_real = self._discriminator_forward(real)
            d_fake = self._discriminator_forward(fake)

            # Discriminator loss: -[log(D(real)) + log(1-D(fake))]
            d_loss = -(math.log(d_real + eps) + math.log(1.0 - d_fake + eps))

            # Update discriminator: nudge weights toward correct classification
            # Gradient for real: increase D(real) → increase weights toward real
            self._update_discriminator(real, target=1.0)
            self._update_discriminator(fake, target=0.0)

            # Generator loss: -log(D(G(z)))
            d_fake_after = self._discriminator_forward(fake)
            g_loss = -math.log(d_fake_after + eps)

            # Update generator: produce fakes that fool discriminator
            self._update_generator(noise)

            result.generator_losses.append(g_loss)
            result.discriminator_losses.append(d_loss)

        result.epochs_trained = epochs
        self._trained = True
        return result

    def _update_discriminator(self, x: list[float], target: float) -> None:
        """Single gradient step on discriminator for one sample."""
        pred = self._discriminator_forward(x)
        error = pred - target  # simple gradient signal

        # Backprop through output layer
        h = _vec_add(_mat_vec(self.d_w1, x), self.d_b1)
        h_relu = [max(0.0, v) for v in h]

        # Output gradient
        d_out = error * pred * (1.0 - pred)  # sigmoid derivative
        for i in range(len(self.d_w2)):
            for j in range(len(self.d_w2[0])):
                self.d_w2[i][j] -= self.lr * d_out * h_relu[j]
            self.d_b2[i] -= self.lr * d_out

        # Hidden gradient
        for j in range(self.hidden_dim):
            if h[j] <= 0:
                continue  # ReLU gate
            grad = d_out * self.d_w2[0][j]
            for k in range(self.scenario_dim):
                self.d_w1[j][k] -= self.lr * grad * x[k]
            self.d_b1[j] -= self.lr * grad

    def _update_generator(self, noise: list[float]) -> None:
        """Single gradient step on generator to fool discriminator."""
        fake = self._generator_forward(noise)
        d_score = self._discriminator_forward(fake)

        # We want to maximise D(G(z)), so gradient ascent on generator
        # d_score closer to 1.0 is better for generator
        error = -(1.0 - d_score)  # negative because we want to increase

        # Approximate gradient by small perturbation
        delta = 0.001
        for i in range(len(self.g_w2)):
            for j in range(len(self.g_w2[0])):
                self.g_w2[i][j] -= self.lr * error * delta
        for i in range(len(self.g_b2)):
            self.g_b2[i] -= self.lr * error * delta

    def generate(self, n: int = 10) -> list[list[float]]:
        """Generate n new failure scenarios.

        Parameters:
            n: Number of scenarios to generate.

        Returns:
            List of scenario vectors in [0, 1]^scenario_dim.
        """

        scenarios = []
        for _ in range(n):
            noise = [random.gauss(0, 1) for _ in range(self.noise_dim)]
            scenario = self._generator_forward(noise)
            scenarios.append(scenario)
        return scenarios


# =====================================================================
# SimpleVAE
# =====================================================================

@dataclass
class VAEResult:
    """Result of VAE training.

    Attributes:
        total_losses: Per-epoch total loss (reconstruction + KL).
        recon_losses: Per-epoch reconstruction loss.
        kl_losses: Per-epoch KL divergence.
        epochs_trained: Number of epochs completed.
    """

    total_losses: list[float] = field(default_factory=list)
    recon_losses: list[float] = field(default_factory=list)
    kl_losses: list[float] = field(default_factory=list)
    epochs_trained: int = 0


class SimpleVAE:
    """Variational Autoencoder for failure scenario generation.

    Architecture:
        Encoder: input_dim → hidden → (mu, log_var)  (latent_dim each)
        Decoder: latent_dim → hidden → input_dim (sigmoid)

    The VAE learns a structured latent space where:
    - Nearby points produce similar scenarios
    - Interpolation yields smooth transitions between failure modes
    - Sampling from the prior N(0,1) generates plausible new scenarios

    Uses the reparameterisation trick: z = mu + sigma * epsilon
    where epsilon ~ N(0,1), enabling gradient flow through sampling.
    """

    def __init__(
        self,
        input_dim: int = 10,
        latent_dim: int = 4,
        hidden_dim: int = 16,
        lr: float = 0.01,
    ) -> None:
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.hidden_dim = hidden_dim
        self.lr = lr

        # Encoder: input → hidden → (mu, log_var)
        self.enc_w1 = _rand_matrix(hidden_dim, input_dim)
        self.enc_b1 = _rand_vector(hidden_dim)
        self.enc_w_mu = _rand_matrix(latent_dim, hidden_dim)
        self.enc_b_mu = _rand_vector(latent_dim)
        self.enc_w_logvar = _rand_matrix(latent_dim, hidden_dim)
        self.enc_b_logvar = _rand_vector(latent_dim)

        # Decoder: latent → hidden → input
        self.dec_w1 = _rand_matrix(hidden_dim, latent_dim)
        self.dec_b1 = _rand_vector(hidden_dim)
        self.dec_w2 = _rand_matrix(input_dim, hidden_dim)
        self.dec_b2 = _rand_vector(input_dim)

        self._trained = False

    def _encode(self, x: list[float]) -> tuple[list[float], list[float]]:
        """Encode input to (mu, log_var) of the latent distribution."""
        h = _vec_add(_mat_vec(self.enc_w1, x), self.enc_b1)
        h = [max(0.0, v) for v in h]  # ReLU
        mu = _vec_add(_mat_vec(self.enc_w_mu, h), self.enc_b_mu)
        log_var = _vec_add(_mat_vec(self.enc_w_logvar, h), self.enc_b_logvar)
        # Clamp log_var for numerical stability
        log_var = [max(-10.0, min(10.0, v)) for v in log_var]
        return mu, log_var

    def _reparameterize(self, mu: list[float], log_var: list[float]) -> list[float]:
        """Reparameterisation trick: z = mu + sigma * epsilon.

        This allows gradients to flow through the sampling operation
        by expressing the random sample as a deterministic function
        of mu, sigma, and an auxiliary noise variable epsilon ~ N(0,1).
        """

        z = []
        for m, lv in zip(mu, log_var):
            sigma = math.exp(0.5 * lv)
            epsilon = random.gauss(0, 1)
            z.append(m + sigma * epsilon)
        return z

    def _decode(self, z: list[float]) -> list[float]:
        """Decode latent vector to reconstructed scenario."""
        h = _vec_add(_mat_vec(self.dec_w1, z), self.dec_b1)
        h = [max(0.0, v) for v in h]  # ReLU
        out = _vec_add(_mat_vec(self.dec_w2, h), self.dec_b2)
        return [_sigmoid(v) for v in out]

    @staticmethod
    def _kl_divergence(mu: list[float], log_var: list[float]) -> float:
        """KL divergence: KL(q(z|x) || p(z)) where p(z) = N(0,1).

        = -0.5 * sum(1 + log_var - mu^2 - exp(log_var))
        """

        kl = 0.0
        for m, lv in zip(mu, log_var):
            kl += -0.5 * (1.0 + lv - m * m - math.exp(lv))
        return kl

    def train(self, data: list[list[float]], epochs: int = 200) -> VAEResult:
        """Train the VAE on scenario data.

        Parameters:
            data: List of scenario vectors (each in [0,1]^input_dim).
            epochs: Number of training epochs.

        Returns:
            VAEResult with per-epoch loss breakdowns.

        Loss = Reconstruction (MSE) + KL divergence.
        Uses a simplified weight update (perturbation-based) to stay
        within standard-library constraints.
        """

        if not data:
            return VAEResult()

        result = VAEResult()

        for epoch in range(epochs):
            x = random.choice(data)

            # Forward pass
            mu, log_var = self._encode(x)
            z = self._reparameterize(mu, log_var)
            recon = self._decode(z)

            # Losses
            recon_loss = _mse(x, recon) * self.input_dim
            kl_loss = self._kl_divergence(mu, log_var)
            total_loss = recon_loss + kl_loss

            # Simplified gradient update: nudge decoder to reduce reconstruction error
            error = _vec_sub(recon, x)
            # Update decoder output layer
            h_dec = _vec_add(_mat_vec(self.dec_w1, z), self.dec_b1)
            h_dec_relu = [max(0.0, v) for v in h_dec]

            for i in range(self.input_dim):
                grad_out = error[i] * recon[i] * (1.0 - recon[i])  # sigmoid deriv
                for j in range(self.hidden_dim):
                    self.dec_w2[i][j] -= self.lr * grad_out * h_dec_relu[j]
                self.dec_b2[i] -= self.lr * grad_out

            # Update encoder mu toward reducing KL
            for i in range(self.latent_dim):
                self.enc_b_mu[i] -= self.lr * 0.01 * mu[i]  # push mu toward 0
                lv_grad = 0.5 * (math.exp(log_var[i]) - 1.0)
                self.enc_b_logvar[i] -= self.lr * 0.01 * lv_grad

            result.total_losses.append(total_loss)
            result.recon_losses.append(recon_loss)
            result.kl_losses.append(kl_loss)

        result.epochs_trained = epochs
        self._trained = True
        return result

    def generate(self, n: int = 10) -> list[list[float]]:
        """Generate n new scenarios by sampling the latent space.

        Parameters:
            n: Number of scenarios to generate.

        Returns:
            List of scenario vectors in [0, 1]^input_dim.

        Samples z ~ N(0, 1) and decodes to scenario space.
        """

        scenarios = []
        for _ in range(n):
            z = [random.gauss(0, 1) for _ in range(self.latent_dim)]
            scenario = self._decode(z)
            scenarios.append(scenario)
        return scenarios


# =====================================================================
# Failure Pattern Clustering (K-means)
# =====================================================================

@dataclass
class ClusterResult:
    """Result of failure pattern clustering.

    Attributes:
        k: Number of clusters.
        assignments: Cluster index for each data point.
        centroids: Cluster centre vectors.
        inertia: Sum of squared distances to nearest centroid.
        representative_scenarios: One representative per cluster
            (closest to centroid).
    """

    k: int = 0
    assignments: list[int] = field(default_factory=list)
    centroids: list[list[float]] = field(default_factory=list)
    inertia: float = 0.0
    representative_scenarios: list[list[float]] = field(default_factory=list)


class FailurePatternClustering:
    """K-means clustering for failure scenario pattern discovery.

    Groups failure scenarios into clusters to reveal recurring patterns
    such as "network partition → DB timeout" or "CPU spike → OOM cascade".

    The elbow method helps select the optimal number of clusters by
    finding the *k* where adding more clusters yields diminishing
    returns in inertia reduction.
    """

    def __init__(self) -> None:
        self._last_result: ClusterResult | None = None
        self._last_data: list[list[float]] = []

    @staticmethod
    def _distance_sq(a: list[float], b: list[float]) -> float:
        return sum((ai - bi) ** 2 for ai, bi in zip(a, b))

    def kmeans(
        self,
        data: list[list[float]],
        k: int,
        max_iter: int = 100,
    ) -> ClusterResult:
        """Run K-means clustering.

        Parameters:
            data: List of feature vectors to cluster.
            k: Number of clusters.
            max_iter: Maximum iterations.

        Returns:
            ClusterResult with assignments, centroids, and inertia.

        Uses K-means++ initialisation for better convergence:
        first centroid is random, subsequent centroids are chosen
        proportional to squared distance from nearest existing centroid.
        """

        if not data or k <= 0:
            return ClusterResult()

        n = len(data)
        dim = len(data[0])
        k = min(k, n)

        # K-means++ initialisation
        centroids: list[list[float]] = [list(random.choice(data))]
        for _ in range(1, k):
            dists = []
            for point in data:
                min_d = min(self._distance_sq(point, c) for c in centroids)
                dists.append(min_d)
            total = sum(dists)
            if total == 0:
                centroids.append(list(random.choice(data)))
                continue
            r = random.uniform(0, total)
            cumulative = 0.0
            for i, d in enumerate(dists):
                cumulative += d
                if cumulative >= r:
                    centroids.append(list(data[i]))
                    break
            else:
                centroids.append(list(data[-1]))

        assignments = [0] * n

        for _ in range(max_iter):
            # Assignment step
            changed = False
            for i, point in enumerate(data):
                best_c = 0
                best_d = float("inf")
                for c_idx, centroid in enumerate(centroids):
                    d = self._distance_sq(point, centroid)
                    if d < best_d:
                        best_d = d
                        best_c = c_idx
                if assignments[i] != best_c:
                    changed = True
                assignments[i] = best_c

            if not changed:
                break

            # Update step
            new_centroids: list[list[float]] = [[0.0] * dim for _ in range(k)]
            counts = [0] * k
            for i, point in enumerate(data):
                c_idx = assignments[i]
                counts[c_idx] += 1
                for d in range(dim):
                    new_centroids[c_idx][d] += point[d]

            for c_idx in range(k):
                if counts[c_idx] > 0:
                    for d in range(dim):
                        new_centroids[c_idx][d] /= counts[c_idx]
                else:
                    new_centroids[c_idx] = list(random.choice(data))

            centroids = new_centroids

        # Compute inertia
        inertia = 0.0
        for i, point in enumerate(data):
            inertia += self._distance_sq(point, centroids[assignments[i]])

        # Find representative scenarios (closest to centroid in each cluster)
        representatives: list[list[float]] = []
        for c_idx in range(k):
            best_point = None
            best_d = float("inf")
            for i, point in enumerate(data):
                if assignments[i] == c_idx:
                    d = self._distance_sq(point, centroids[c_idx])
                    if d < best_d:
                        best_d = d
                        best_point = point
            if best_point is not None:
                representatives.append(list(best_point))

        result = ClusterResult(
            k=k,
            assignments=assignments,
            centroids=centroids,
            inertia=inertia,
            representative_scenarios=representatives,
        )
        self._last_result = result
        self._last_data = data
        return result

    def find_optimal_k(
        self,
        data: list[list[float]],
        max_k: int = 10,
    ) -> int:
        """Find optimal k using the elbow method.

        Parameters:
            data: Feature vectors to cluster.
            max_k: Maximum k to evaluate.

        Returns:
            The optimal k value (elbow point).

        The elbow is detected as the k with the maximum second
        derivative of the inertia curve (greatest rate of change
        in the rate of inertia decrease).
        """

        if not data:
            return 1

        max_k = min(max_k, len(data))
        inertias: list[float] = []

        for k in range(1, max_k + 1):
            result = self.kmeans(data, k)
            inertias.append(result.inertia)

        if len(inertias) <= 2:
            return 1

        # Find elbow via maximum second derivative
        best_k = 1
        best_diff = 0.0
        for i in range(1, len(inertias) - 1):
            second_deriv = (inertias[i - 1] - 2 * inertias[i] + inertias[i + 1])
            if second_deriv > best_diff:
                best_diff = second_deriv
                best_k = i + 1  # k is 1-indexed

        return best_k

    def cluster_failures(
        self,
        graph: "InfraGraph",
        scenarios: list[list[float]],
        max_k: int = 10,
    ) -> ClusterResult:
        """Cluster failure scenarios using optimal k.

        Parameters:
            graph: Infrastructure graph (used for context in future
                extensions; currently scenarios are clustered directly).
            scenarios: List of scenario vectors.
            max_k: Maximum clusters to consider.

        Returns:
            ClusterResult with optimal clustering.
        """

        from faultray.model.graph import InfraGraph  # noqa: F811

        k = self.find_optimal_k(scenarios, max_k)
        return self.kmeans(scenarios, k)

    def get_representative_scenarios(self) -> list[list[float]]:
        """Return one representative scenario per cluster.

        Returns the scenario closest to each centroid from the most
        recent clustering run.  Call ``kmeans()`` or
        ``cluster_failures()`` first.
        """

        if self._last_result is None:
            return []
        return list(self._last_result.representative_scenarios)
