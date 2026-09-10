import math
import torch
import pytest
import numpy as np
from akasha_2_lite.models.hamiltonian_ssm import HamiltonianLatentModel
from akasha_2_lite.models.baseline_ssm import BaselineDynamicalModel

def make_canonical_J(dim: int) -> torch.Tensor:
    """Create standard symplectic matrix J of size 2*dim x 2*dim."""
    I = torch.eye(dim)
    Z = torch.zeros(dim, dim)
    top = torch.cat([Z, I], dim=1)
    bottom = torch.cat([-I, Z], dim=1)
    return torch.cat([top, bottom], dim=0)


class TestSymplecticGeometry:
    """Rigorous tests of symplectic geometry, Liouville's theorem, and Jacobians."""

    def test_symplectic_matrix_properties(self):
        """J must satisfy J^T = -J, J^2 = -I, and det(J) = 1."""
        for d in [1, 2, 3]:
            J = make_canonical_J(d)
            # Skew-symmetry
            assert torch.allclose(J.T, -J), "J must be skew-symmetric"
            # J^2 = -I
            assert torch.allclose(J @ J, -torch.eye(2 * d)), "J^2 must equal -I"
            # det(J) = 1
            det_J = torch.det(J).item()
            assert math.isclose(det_J, 1.0, abs_tol=1e-5), f"det(J) must be 1, got {det_J}"

    def test_canonical_equations_divergence_free(self):
        """
        By Liouville's theorem, any Hamiltonian vector field has div(f) = 0.
        div(f) = sum_i d/dq_i (dH/dp_i) + sum_i d/dp_i (-dH/dq_i)
               = sum_i (d^2 H / dq_i dp_i - d^2 H / dp_i dq_i) = 0 (by Clairaut-Schwarz theorem).
        """
        model = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=64)
        model.train() # allow higher-order autograd

        q = torch.tensor([1.3], requires_grad=True)
        p = torch.tensor([-0.8], requires_grad=True)

        dq_dt, dp_dt = model.time_derivatives(q, p)

        # Compute d/dq(dq/dt) and d/dp(dp_dt)
        d_dq_dqdt = torch.autograd.grad(dq_dt, q, retain_graph=True)[0]
        d_dp_dpdt = torch.autograd.grad(dp_dt, p, retain_graph=True)[0]

        divergence = d_dq_dqdt + d_dp_dpdt
        assert torch.abs(divergence).item() < 1e-5, f"Hamiltonian divergence must vanish, got {divergence.item()}"

    def test_leapfrog_near_symplecticity(self):
        """
        Test that explicit leapfrog on H_theta preserves volume within O(dt^2)
        and exhibits bounded symplectic violation.
        """
        model = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=64)
        model.train()
        dt = 0.05
        J = make_canonical_J(1)

        for state_val in [[0.5, 0.5], [1.2, -0.7], [-1.0, 1.5]]:
            x = torch.tensor(state_val, dtype=torch.float32)

            def step_fn(s):
                d = model.coordinate_dim
                q = s[:d]
                p = s[d:]
                dq_1, dp_1 = model.time_derivatives(q, p)
                p_half = p + 0.5 * dt * dp_1
                dq_2, _ = model.time_derivatives(q, p_half)
                q_next = q + dt * dq_2
                _, dp_3 = model.time_derivatives(q_next, p_half)
                p_next = p_half + 0.5 * dt * dp_3
                return torch.cat([q_next, p_next], dim=-1)

            DPhi = torch.autograd.functional.jacobian(step_fn, x)
            det = torch.det(DPhi).item()
            assert abs(det - 1.0) < 1e-3, f"Volume deviation too large: {abs(det - 1.0)}"

            symp_mat = DPhi.T @ J @ DPhi
            symp_err = torch.norm(symp_mat - J).item()
            assert symp_err < 1e-3, f"Symplectic violation too large: {symp_err}"


class TestBackwardErrorAnalysis:
    """Verify shadow Hamiltonian and bounded energy drift vs secular RK4 drift."""

    def test_symplectic_vs_rk4_long_horizon_drift(self):
        """
        For a harmonic oscillator (H = 0.5 * p^2 + 0.5 * k * q^2),
        a symplectic leapfrog integrator must exhibit bounded energy oscillations O(dt^2),
        whereas forward Euler or unconstrained integrators display monotonic secular drift.
        """
        dt = 0.05
        n_steps = 2000
        k = 2.0
        m = 1.0

        def exact_H(q, p):
            return 0.5 * (p**2) / m + 0.5 * k * (q**2)

        # 1. Symplectic Leapfrog
        q_lf, p_lf = 1.0, 0.0
        H0 = exact_H(q_lf, p_lf)
        lf_energies = [H0]

        for _ in range(n_steps):
            p_half = p_lf - 0.5 * dt * (k * q_lf)
            q_lf = q_lf + dt * (p_half / m)
            p_lf = p_half - 0.5 * dt * (k * q_lf)
            lf_energies.append(exact_H(q_lf, p_lf))

        # 2. Forward Euler (non-symplectic)
        q_fe, p_fe = 1.0, 0.0
        fe_energies = [H0]
        for _ in range(n_steps):
            dq = (p_fe / m) * dt
            dp = -(k * q_fe) * dt
            q_fe += dq
            p_fe += dp
            fe_energies.append(exact_H(q_fe, p_fe))

        lf_energies = np.array(lf_energies)
        fe_energies = np.array(fe_energies)

        lf_max_drift = np.max(np.abs(lf_energies - H0)) / H0
        fe_final_drift = np.abs(fe_energies[-1] - H0) / H0

        assert lf_max_drift < 0.01, f"Symplectic leapfrog exceeded bounded energy threshold: {lf_max_drift}"
        assert fe_final_drift > 10.0, f"Forward Euler expected to diverge, got {fe_final_drift}"

        # Zero secular drift slope
        steps = np.arange(len(lf_energies))
        slope, _ = np.polyfit(steps, lf_energies, 1)
        assert abs(slope) < 1e-6, f"Leapfrog has non-zero secular drift slope: {slope}"


class TestSeparableAndPortHamiltonian:
    """Verify exact symplecticity of Separable HNN and passivity of Port-Hamiltonian."""

    def test_separable_exact_symplecticity(self):
        """
        For separable H(q, p) = T(p) + V(q), the Leapfrog integrator
        is a composition of shears, so det(DPhi) == 1.0 down to float precision.
        """
        from akasha_2_lite.models.separable_hamiltonian import SeparableHamiltonianModel

        model = SeparableHamiltonianModel(coordinate_dim=1, hidden_dim=64)
        model.train()
        dt = 0.05
        J = make_canonical_J(1)

        for state_val in [[0.8, -0.4], [-1.5, 0.2], [0.1, 1.1]]:
            x = torch.tensor(state_val, dtype=torch.float32)

            def step_fn(s):
                d = model.coordinate_dim
                q = s[:d]
                p = s[d:]
                v1 = model.potential_energy(q).sum()
                grad_v1 = torch.autograd.grad(v1, q, create_graph=True)[0]
                p_half = p - 0.5 * dt * grad_v1

                t_half = model.kinetic_energy(p_half).sum()
                grad_t = torch.autograd.grad(t_half, p_half, create_graph=True)[0]
                q_next = q + dt * grad_t

                v2 = model.potential_energy(q_next).sum()
                grad_v2 = torch.autograd.grad(v2, q_next, create_graph=True)[0]
                p_next = p_half - 0.5 * dt * grad_v2
                return torch.cat([q_next, p_next], dim=-1)

            DPhi = torch.autograd.functional.jacobian(step_fn, x)
            det = torch.det(DPhi).item()
            # Exact volume preservation
            assert abs(det - 1.0) < 1e-6, f"Separable HNN det deviation too large: {abs(det - 1.0)}"

            symp_mat = DPhi.T @ J @ DPhi
            symp_err = torch.norm(symp_mat - J).item()
            assert symp_err < 1e-5, f"Separable HNN symplectic violation: {symp_err}"

    def test_port_hamiltonian_passivity(self):
        """
        Under Port-Hamiltonian dynamics dx/dt = (J - R) grad H with R = diag(0, D), D >= 0:
        dH/dt = - (grad_p H)^T D (grad_p H) <= 0.
        Energy can NEVER increase spontaneously.
        """
        from akasha_2_lite.models.port_hamiltonian_ssm import PortHamiltonianSSM

        model = PortHamiltonianSSM(coordinate_dim=1, hidden_dim=64, init_damping=0.2)
        model.train()

        states = torch.randn(20, 2)
        q = states[:, :1]
        p = states[:, 1:]

        dq_dt, dp_dt = model.time_derivatives(q, p)
        
        # dH/dt = (dH/dq)*dq_dt + (dH/dp)*dp_dt
        with torch.enable_grad():
            q_in = q.clone().detach().requires_grad_(True)
            p_in = p.clone().detach().requires_grad_(True)
            h = model.energy(q_in, p_in)
            grad_q, grad_p = torch.autograd.grad(h.sum(), [q_in, p_in])

        dH_dt = grad_q * dq_dt + grad_p * dp_dt
        
        # For each sample in batch, dH/dt must be non-positive (<= 1e-6 numerical tolerance)
        for val in dH_dt.flatten():
            assert val.item() <= 1e-6, f"Port-Hamiltonian violated passivity: dH/dt = {val.item()}"


class TestModelArchitecturesAndPipelines:
    """Verify architectural invariants, multi-step loaders, and parameter guarantees."""

    def test_all_models_rollout_shapes(self):
        from akasha_2_lite.models import (
            BaselineDynamicalModel,
            HamiltonianLatentModel,
            SeparableHamiltonianModel,
            PortHamiltonianSSM,
        )

        batch_size = 8
        n_steps = 25
        dt = 0.05
        x0 = torch.randn(batch_size, 2)

        models = [
            BaselineDynamicalModel(state_dim=2, hidden_dim=64),
            HamiltonianLatentModel(coordinate_dim=1, hidden_dim=64),
            SeparableHamiltonianModel(coordinate_dim=1, hidden_dim=48),
            PortHamiltonianSSM(coordinate_dim=1, hidden_dim=64),
        ]

        for m in models:
            m.eval()
            with torch.no_grad():
                out = m.rollout(x0, n_steps=n_steps, dt=dt)
                assert out.shape == (batch_size, n_steps, 2), f"Failed for {type(m).__name__}"

    def test_multistep_loader_shapes(self):
        from akasha_2_lite.training import prepare_multistep_loader

        N, T, D = 10, 50, 2
        horizon = 5
        dummy_trajs = torch.randn(N, T, D)
        loader = prepare_multistep_loader(dummy_trajs, horizon=horizon, batch_size=16)

        for x_init, x_targets in loader:
            assert x_init.shape == (x_init.shape[0], D)
            assert x_targets.shape == (x_init.shape[0], horizon, D)
            break

    def test_port_hamiltonian_strictly_non_negative_damping(self):
        from akasha_2_lite.models import PortHamiltonianSSM

        m = PortHamiltonianSSM(coordinate_dim=1, hidden_dim=32)
        # Even with extreme negative raw parameters, softplus guarantees D >= 0
        m.raw_damping.data.fill_(-100.0)
        assert m.damping.item() >= 0.0
        assert m.damping.item() < 1e-10

        m.raw_damping.data.fill_(10.0)
        assert m.damping.item() > 9.99
