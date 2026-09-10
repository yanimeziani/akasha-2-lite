import torch
import torch.nn as nn
from typing import Tuple

class SeparableHamiltonianModel(nn.Module):
    """
    Separable Hamiltonian Neural Network:
    H(q, p) = T_theta(p) + V_psi(q)
    
    By separating kinetic and potential energy, the Störmer-Verlet / Leapfrog
    integration map is mathematically proven to be EXACTLY symplectic:
    DPhi^T J DPhi = J identically, with det(DPhi) = 1.0 down to floating-point precision.
    """

    def __init__(self, coordinate_dim: int = 1, hidden_dim: int = 92):
        super().__init__()
        self.coordinate_dim = coordinate_dim
        
        # Kinetic energy network T(p)
        self.kinetic_net = nn.Sequential(
            nn.Linear(coordinate_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )
        
        # Potential energy network V(q)
        self.potential_net = nn.Sequential(
            nn.Linear(coordinate_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )

    def kinetic_energy(self, p: torch.Tensor) -> torch.Tensor:
        return self.kinetic_net(p)

    def potential_energy(self, q: torch.Tensor) -> torch.Tensor:
        return self.potential_net(q)

    def energy(self, q: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
        """Total Hamiltonian H(q, p) = T(p) + V(q)."""
        return self.kinetic_energy(p) + self.potential_energy(q)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        d = self.coordinate_dim
        q = x[..., :d]
        p = x[..., d:]
        return self.energy(q, p)

    def time_derivatives(self, q: torch.Tensor, p: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        dq/dt =  dT/dp
        dp/dt = -dV/dq
        """
        with torch.enable_grad():
            q_in = q if q.requires_grad else q.clone().detach().requires_grad_(True)
            p_in = p if p.requires_grad else p.clone().detach().requires_grad_(True)

            v = self.potential_energy(q_in)
            t = self.kinetic_energy(p_in)

            dV_dq = torch.autograd.grad(
                outputs=v.sum(),
                inputs=q_in,
                create_graph=self.training,
                retain_graph=True,
            )[0]

            dT_dp = torch.autograd.grad(
                outputs=t.sum(),
                inputs=p_in,
                create_graph=self.training,
                retain_graph=True,
            )[0]

            dq_dt = dT_dp
            dp_dt = -dV_dq
            return dq_dt, dp_dt

    def forward_step(self, x: torch.Tensor, dt: float) -> torch.Tensor:
        """
        Exact Symplectic Leapfrog / Störmer-Verlet scheme:
        1. p_{t+1/2} = p_t - (dt / 2) * dV/dq(q_t)
        2. q_{t+1}   = q_t + dt * dT/dp(p_{t+1/2})
        3. p_{t+1}   = p_{t+1/2} - (dt / 2) * dV/dq(q_{t+1})
        """
        d = self.coordinate_dim
        q = x[..., :d]
        p = x[..., d:]

        with torch.enable_grad():
            q_in = q if q.requires_grad else q.clone().detach().requires_grad_(True)
            v1 = self.potential_energy(q_in).sum()
            grad_v1 = torch.autograd.grad(
                outputs=v1,
                inputs=q_in,
                create_graph=self.training,
                retain_graph=True,
            )[0]

        # 1. Half-step momentum
        p_half = p - 0.5 * dt * grad_v1

        # 2. Full-step position
        with torch.enable_grad():
            p_half_in = p_half if p_half.requires_grad else p_half.clone().detach().requires_grad_(True)
            t_half = self.kinetic_energy(p_half_in).sum()
            grad_t = torch.autograd.grad(
                outputs=t_half,
                inputs=p_half_in,
                create_graph=self.training,
                retain_graph=True,
            )[0]

        q_next = q + dt * grad_t

        # 3. Half-step momentum
        with torch.enable_grad():
            q_next_in = q_next if q_next.requires_grad else q_next.clone().detach().requires_grad_(True)
            v2 = self.potential_energy(q_next_in).sum()
            grad_v2 = torch.autograd.grad(
                outputs=v2,
                inputs=q_next_in,
                create_graph=self.training,
                retain_graph=True,
            )[0]

        p_next = p_half - 0.5 * dt * grad_v2

        return torch.cat([q_next, p_next], dim=-1)

    def rollout(self, x0: torch.Tensor, n_steps: int, dt: float) -> torch.Tensor:
        traj = [x0]
        curr_x = x0
        for _ in range(n_steps - 1):
            curr_x = self.forward_step(curr_x, dt)
            traj.append(curr_x)
        return torch.stack(traj, dim=1)
