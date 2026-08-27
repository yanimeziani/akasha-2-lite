# AKASHA 2-Lite: Experimental Results

**Hypothesis:** Does a Hamiltonian latent-state module improve long-horizon prediction stability over an ordinary state-space baseline?

| Dataset | Architecture | Horizon-50 MSE | Horizon-100 MSE | Horizon-200 MSE | Energy Drift (ΔH/H₀) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ideal Pendulum** | Baseline SSM | 0.0001 ± 0.0000 | 0.0003 ± 0.0002 | 0.0024 ± 0.0019 | 0.0131 ± 0.0049 |
| **Ideal Pendulum** | **Hamiltonian SSM (Ours)** | **0.0010 ± 0.0003** | **0.0043 ± 0.0016** | **0.0294 ± 0.0084** | **0.0109 ± 0.0014** |
| **Harmonic Oscillator** | Baseline SSM | 0.0008 ± 0.0002 | 0.0028 ± 0.0005 | 0.0101 ± 0.0023 | 0.0055 ± 0.0005 |
| **Harmonic Oscillator** | **Hamiltonian SSM (Ours)** | **0.0023 ± 0.0021** | **0.0080 ± 0.0054** | **0.0360 ± 0.0262** | **0.0092 ± 0.0022** |
| **Damped Pendulum (Dissipative)** | Baseline SSM | 0.0001 ± 0.0000 | 0.0001 ± 0.0001 | 0.0001 ± 0.0001 | 0.5639 ± 0.0052 |
| **Damped Pendulum (Dissipative)** | **Hamiltonian SSM (Ours)** | **0.0299 ± 0.0010** | **0.1222 ± 0.0058** | **0.3523 ± 0.0377** | **0.0682 ± 0.0018** |