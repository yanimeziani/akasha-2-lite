import json
import os
import torch
import numpy as np

from akasha_2_lite.data import IdealPendulum
from akasha_2_lite.models import BaselineDynamicalModel, HamiltonianLatentModel
from akasha_2_lite.training import prepare_transition_loader, train_dynamical_model

def main():
    seed = 42
    torch.manual_seed(seed)
    np.random.seed(seed)

    dt = 0.05
    pendulum = IdealPendulum(g=3.0)

    print("Generating training data for demo models...")
    train_data, _ = pendulum.generate_trajectories(
        n_trajectories=160, n_steps=60, dt=dt, seed=seed
    )
    train_loader = prepare_transition_loader(train_data, batch_size=128, shuffle=True)

    print("Training Baseline SSM...")
    baseline = BaselineDynamicalModel(state_dim=2, hidden_dim=128)
    train_dynamical_model(baseline, train_loader, dt=dt, epochs=40)

    print("Training Hamiltonian SSM...")
    hamiltonian = HamiltonianLatentModel(coordinate_dim=1, hidden_dim=128)
    train_dynamical_model(hamiltonian, train_loader, dt=dt, epochs=40)

    baseline.eval()
    hamiltonian.eval()

    # Extract weights
    def extract_mlp_weights(sequential_net):
        layers = []
        # sequential_net has Linear(0), Tanh(1), Linear(2), Tanh(3), Linear(4)
        for idx in [0, 2, 4]:
            layer = sequential_net[idx]
            layers.append({
                "w": layer.weight.detach().cpu().numpy().tolist(), # [out_dim, in_dim]
                "b": layer.bias.detach().cpu().numpy().tolist(),   # [out_dim]
            })
        return layers

    export_data = {
        "metadata": {
            "g": 3.0,
            "dt": 0.05,
            "seed": 42,
            "description": "AKASHA 2-Lite trained weights for real-time browser inference",
        },
        "baseline": extract_mlp_weights(baseline.net),
        "hamiltonian": extract_mlp_weights(hamiltonian.net),
    }

    os.makedirs("demo", exist_ok=True)
    out_file = "demo/weights.json"
    with open(out_file, "w") as f:
        json.dump(export_data, f)

    size_kb = os.path.getsize(out_file) / 1024.0
    print(f"[OK] Exported weights to {out_file} ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
