import torch
from akasha_2_lite.models import BaselineDynamicalModel, HamiltonianLatentModel
from akasha_2_lite.metrics import measure_model_efficiency

def main():
    print("--- Checking Model Architectures and Parameter Counts ---")
    baseline = BaselineDynamicalModel(state_dim=2, hidden_dim=128)
    hamiltonian = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=128)

    sample_x = torch.randn(16, 2)
    dt = 0.05

    base_eff = measure_model_efficiency(baseline, sample_x)
    print(f"Baseline Parameters:    {base_eff['total_parameters']:,}")
    print(f"Baseline Mean Latency:  {base_eff['mean_latency_ms']:.3f} ms")

    ham_eff = measure_model_efficiency(hamiltonian.net, sample_x)
    print(f"Hamiltonian Parameters: {ham_eff['total_parameters']:,}")

    # Test single steps and rollouts
    base_step = baseline.forward_step(sample_x, dt)
    assert base_step.shape == (16, 2), f"Expected (16, 2), got {base_step.shape}"

    ham_step = hamiltonian.forward_step(sample_x, dt)
    assert ham_step.shape == (16, 2), f"Expected (16, 2), got {ham_step.shape}"

    # Test rollouts
    base_roll = baseline.rollout(sample_x, n_steps=50, dt=dt)
    ham_roll = hamiltonian.rollout(sample_x, n_steps=50, dt=dt)
    assert base_roll.shape == (16, 50, 2), f"Expected (16, 50, 2), got {base_roll.shape}"
    assert ham_roll.shape == (16, 50, 2), f"Expected (16, 50, 2), got {ham_roll.shape}"

    print(f"Baseline Rollout Shape:    {base_roll.shape}")
    print(f"Hamiltonian Rollout Shape: {ham_roll.shape}")
    print("[OK] Both models initialized and verified successfully!")

if __name__ == "__main__":
    main()
