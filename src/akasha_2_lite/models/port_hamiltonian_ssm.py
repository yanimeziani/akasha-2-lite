import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple

class PortHamiltonianSSM(nn.Module):
    """
    Port-Hamiltonian State-Space Model:
    Dynamics governed by:
        dx/dt = (J - R(x)) * grad_x H(x)
    where:
        J = [[0, I], [-I, 0]] is the skew-symmetric symplectic interconnection matrix
        R = [[0, 0], [0, D]] is the positive semi-definite dissipation matrix with D >= 0

    Scalar energy evolution:
        dH/dt = (grad_x H)^T (J - R) (grad_x H)
              = - (grad_p H)^T D (grad_p H) <= 0
    Passivity (energy non-increase) is structurally and mathematically guaranteed.
    When D = 0, this strictly recovers the conservative Hamiltonian SSM.
    """

    def __init__(self, coordinate_dim: int = 1, hidden_dim: int = 128, init_damping: float = 0.01):
        super().__init__()
        self.coordinate_dim = coordinate_dim
        state_dim = 2 * coordinate_dim
        
        # Energy MLP H_theta(q, p)
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, 1),
        )

        # Learnable unconstrained parameter mapped to positive damping via softplus
        # softplus(x) = log(1 + exp(x)) >= 0
        init_raw = torch.log(torch.exp(torch.tensor(init_damping)) - 1.0) if init_damping > 1e-4 else torch.tensor(-5.0)
        self.raw_damping = nn.Parameter(torch.full((coordinate_dim,), float(init_raw)))

    @property
    def damping(self) -> torch.Tensor:
        """Non-negative dissipation coefficient D >= 0."""
        return F.softplus(self.raw_damping)

    def energy(self, q: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
        state = torch.cat([q, p], dim=-1)
        return self.net(state)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)

    def conservative_time_derivatives(self, q: torch.Tensor, p: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
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
            return grad_p, -grad_q

    def time_derivatives(self, q: torch.Tensor, p: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Port-Hamiltonian equations of motion:
        dq/dt =  dH/dp
        dp/dt = -dH/dq - D * dH/dp
        """
        dq_dt, dp_dt_conservative = self.conservative_time_derivatives(q, p)
        dp_dt = dp_dt_conservative - self.damping * dq_dt
        return dq_dt, dp_dt

    def forward_step(self, x: torch.Tensor, dt: float) -> torch.Tensor:
        """
        Symplectic-Dissipative Strang Splitting:
        1. Half-step conservative kick: p_{1/2} = p - (dt/2) * dH/dq(q, p)
        2. Dissipative decay step:      p_{1/2}' = p_{1/2} * exp(-D * dt)
        3. Full-step drift:             q_{next} = q + dt * dH/dp(q, p_{1/2}')
        4. Half-step conservative kick: p_{next} = p_{1/2}' - (dt/2) * dH/dq(q_{next}, p_{1/2}')
        """
        d = self.coordinate_dim
        q = x[..., :d]
        p = x[..., d:]

        # Step 1: Half-step potential kick
        _, dp_dt_1 = self.conservative_time_derivatives(q, p)
        p_half = p + 0.5 * dt * dp_dt_1

        # Step 2: Dissipation step via exact exponential flow
        damp_factor = torch.exp(-self.damping * dt)
        p_damped = p_half * damp_factor

        # Step 3: Full-step position drift
        dq_dt_2, _ = self.conservative_time_derivatives(q, p_damped)
        q_next = q + dt * dq_dt_2

        # Step 4: Half-step potential kick
        _, dp_dt_3 = self.conservative_time_derivatives(q_next, p_damped)
        p_next = p_damped + 0.5 * dt * dp_dt_3

        return torch.cat([q_next, p_next], dim=-1)

    def rollout(self, x0: torch.Tensor, n_steps: int, dt: float) -> torch.Tensor:
        traj = [x0]
        curr_x = x0
        for _ in range(n_steps - 1):
            curr_x = self.forward_step(curr_x, dt)
            traj.append(curr_x)
        return torch.stack(traj, dim=1)
