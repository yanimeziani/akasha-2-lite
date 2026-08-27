import numpy as np
import torch
from scipy.integrate import solve_ivp
from typing import Tuple
from akasha_2_lite.data.base import DynamicalSystem

class HarmonicOscillator(DynamicalSystem):
    """
    Linear harmonic oscillator (mass-spring system).
    State: [q, p] where q is displacement and p is momentum (m=1).
    H(q, p) = 0.5 * p^2 + 0.5 * k * q^2
    dq/dt = p
    dp/dt = -k * q
    """

    def __init__(self, k: float = 2.0, m: float = 1.0):
        self.k = k
        self.m = m

    def hamiltonian(self, q: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
        kinetic = 0.5 * (p ** 2)
        potential = 0.5 * self.k * (q ** 2)
        return kinetic + potential

    def equations_of_motion(self, t: float, state: np.ndarray) -> np.ndarray:
        q, p = state[0], state[1]
        dq_dt = p
        dp_dt = -self.k * q
        return np.array([dq_dt, dp_dt], dtype=np.float64)

    def sample_initial_conditions(self, n_samples: int, rng: np.random.Generator) -> np.ndarray:
        q0 = rng.uniform(-1.5, 1.5, size=(n_samples, 1))
        p0 = rng.uniform(-1.5, 1.5, size=(n_samples, 1))
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
