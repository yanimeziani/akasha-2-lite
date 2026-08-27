import numpy as np
import torch
from scipy.integrate import solve_ivp
from typing import Tuple
from akasha_2_lite.data.base import DynamicalSystem

class DampedPendulum(DynamicalSystem):
    """
    Non-conservative / Dissipative Pendulum with viscous friction.
    State: [q, p]
    dq/dt = p
    dp/dt = -g * sin(q) - gamma * p
    Total energy decays over time: dH/dt = -gamma * p^2 <= 0.
    """

    def __init__(self, g: float = 3.0, gamma: float = 0.2):
        self.g = g
        self.gamma = gamma

    def hamiltonian(self, q: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
        """Instantaneous mechanical energy H(q, p)."""
        kinetic = 0.5 * (p ** 2)
        potential = self.g * (1.0 - torch.cos(q))
        return kinetic + potential

    def equations_of_motion(self, t: float, state: np.ndarray) -> np.ndarray:
        q, p = state[0], state[1]
        dq_dt = p
        dp_dt = -self.g * np.sin(q) - self.gamma * p
        return np.array([dq_dt, dp_dt], dtype=np.float64)

    def sample_initial_conditions(self, n_samples: int, rng: np.random.Generator) -> np.ndarray:
        q0 = rng.uniform(-1.2, 1.2, size=(n_samples, 1))
        p0 = rng.uniform(-1.0, 1.0, size=(n_samples, 1))
        return np.hstack([q0, p0]).astype(np.float32)

    def generate_trajectories(
        self,
        n_trajectories: int,
        n_steps: int,
        dt: float = 0.05,
        seed: int = 42,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        rng = np.random.default_rng(seed)
        init_states = self.sample_initial_conditions(n_trajectories, rng)

        t_eval = np.linspace(0, (n_steps - 1) * dt, n_steps)
        trajectories = np.zeros((n_trajectories, n_steps, 2), dtype=np.float32)

        for i in range(n_trajectories):
            sol = solve_ivp(
                fun=self.equations_of_motion,
                t_span=(0, t_eval[-1]),
                y0=init_states[i],
                t_eval=t_eval,
                method="DOP853",
                rtol=1e-10,
                atol=1e-10,
            )
            trajectories[i] = sol.y.T.astype(np.float32)

        traj_tensor = torch.from_numpy(trajectories)
        q = traj_tensor[..., 0]
        p = traj_tensor[..., 1]
        energy_tensor = self.hamiltonian(q, p)

        return traj_tensor, energy_tensor
