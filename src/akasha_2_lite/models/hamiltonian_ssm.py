import torch
import torch.nn as nn
from typing import Tuple

class HamiltonianLatentModel(nn.Module):
    """
    Hamiltonian Neural Network with Symplectic Leapfrog Integration:
    Learns scalar energy function H_theta(q, p).
    Equations of motion:
        dq/dt =  dH/dp
        dp/dt = -dH/dq
    Discrete integration preserves symplectic 2-form and bounds energy drift.
    """

    def __init__(self, coordinate_dim: int = 1, hidden_dim: int = 128):
        super().__init__()
        self.coordinate_dim = coordinate_dim # dim of q (total state_dim = 2 * coordinate_dim)
        state_dim = 2 * coordinate_dim
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass computes scalar energy H(x)."""
        return self.net(x)

    def energy(self, q: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
        """Evaluate scalar Hamiltonian H(q, p)."""
        state = torch.cat([q, p], dim=-1)
        return self.forward(state)

    def time_derivatives(self, q: torch.Tensor, p: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Compute dq/dt = dH/dp and dp/dt = -dH/dq via autograd.
        """
        with torch.enable_grad():
            q_in = q if q.requires_grad else q.clone().detach().requires_grad_(True)
            p_in = p if p.requires_grad else p.clone().detach().requires_grad_(True)
            
            h = self.energy(q_in, p_in)
            grad_q, grad_p = torch.autograd.grad(
                outputs=h.sum(),
                inputs=[q_in, p_in],
                create_graph=self.training,
                retain_graph=True,
            )
            dq_dt = grad_p
            dp_dt = -grad_q
            return dq_dt, dp_dt

    def forward_step(self, x: torch.Tensor, dt: float) -> torch.Tensor:
        """
        Symplectic Leapfrog (Verlet) step:
        1. p_{t+1/2} = p_t - (dt/2) * (dH/dq)(q_t, p_t)
        2. q_{t+1}   = q_t + dt * (dH/dp)(q_t, p_{t+1/2})
        3. p_{t+1}   = p_{t+1/2} - (dt/2) * (dH/dq)(q_{t+1}, p_{t+1/2})
        """
        d = self.coordinate_dim
        q = x[..., :d]
        p = x[..., d:]

        # Step 1: Half-step momentum
        dq_dt_1, dp_dt_1 = self.time_derivatives(q, p)
        p_half = p + 0.5 * dt * dp_dt_1

        # Step 2: Full-step position
        dq_dt_2, _ = self.time_derivatives(q, p_half)
        q_next = q + dt * dq_dt_2

        # Step 3: Half-step momentum
        _, dp_dt_3 = self.time_derivatives(q_next, p_half)
        p_next = p_half + 0.5 * dt * dp_dt_3

        return torch.cat([q_next, p_next], dim=-1)

    def rollout(self, x0: torch.Tensor, n_steps: int, dt: float) -> torch.Tensor:
        """
        Autoregressively roll out trajectory for n_steps using symplectic steps.
        Args:
            x0: Initial state [batch_size, 2 * coordinate_dim]
            n_steps: Number of steps to roll out
            dt: Timestep size
        Returns:
            trajectories: [batch_size, n_steps, 2 * coordinate_dim]
        """
        traj = [x0]
        curr_x = x0
        for _ in range(n_steps - 1):
            curr_x = self.forward_step(curr_x, dt)
            traj.append(curr_x)
        return torch.stack(traj, dim=1)
