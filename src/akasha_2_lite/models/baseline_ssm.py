import torch
import torch.nn as nn
from typing import Tuple

class BaselineDynamicalModel(nn.Module):
    """
    Unconstrained state-space dynamical baseline:
    dx/dt = f_theta(x)
    x_{t+1} = x_t + dt * f_theta(x_t)  (or RK4 integration)
    """

    def __init__(self, state_dim: int = 2, hidden_dim: int = 128):
        super().__init__()
        self.state_dim = state_dim
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, state_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass computes dx/dt."""
        return self.net(x)

    def forward_derivative(self, x: torch.Tensor) -> torch.Tensor:
        """Compute dx/dt."""
        return self.forward(x)

    def forward_step(self, x: torch.Tensor, dt: float) -> torch.Tensor:
        """
        Step forward by dt using Runge-Kutta 4 (RK4) or Euler.
        We use RK4 for a strong numerical baseline.
        """
        k1 = self.forward_derivative(x)
        k2 = self.forward_derivative(x + 0.5 * dt * k1)
        k3 = self.forward_derivative(x + 0.5 * dt * k2)
        k4 = self.forward_derivative(x + dt * k3)
        return x + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    def rollout(self, x0: torch.Tensor, n_steps: int, dt: float) -> torch.Tensor:
        """
        Autoregressively roll out trajectory for n_steps.
        Args:
            x0: Initial state [batch_size, state_dim]
            n_steps: Number of steps to roll out
            dt: Timestep size
        Returns:
            trajectories: [batch_size, n_steps, state_dim]
        """
        traj = [x0]
        curr_x = x0
        for _ in range(n_steps - 1):
            curr_x = self.forward_step(curr_x, dt)
            traj.append(curr_x)
        return torch.stack(traj, dim=1)
