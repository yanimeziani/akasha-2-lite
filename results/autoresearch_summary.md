# AKASHA 2-Lite: Autoresearch Benchmark Results

Comprehensive 200-step autoregressive rollout evaluation across 3 seeds (42, 43, 44).

| Dataset | Architecture | Horizon-50 MSE | Horizon-100 MSE | Horizon-200 MSE | Energy Drift ($|\Delta H|/H_0$) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Ideal Pendulum** | Baseline SSM (RK4) | 0.0001 ± 0.0000 | 0.0003 ± 0.0002 | 0.0024 ± 0.0019 | 0.0131 ± 0.0049 |
| **Ideal Pendulum** | Hamiltonian SSM (1-Step) | 0.0010 ± 0.0003 | 0.0043 ± 0.0016 | 0.0294 ± 0.0084 | 0.0109 ± 0.0014 |
| **Ideal Pendulum** | Separable HNN (Multi-Step) | 0.0000 ± 0.0000 | 0.0001 ± 0.0000 | 0.0003 ± 0.0002 | 0.0007 ± 0.0001 |
| **Ideal Pendulum** | Port-Hamiltonian SSM (Multi-Step) | 0.0008 ± 0.0000 | 0.0049 ± 0.0003 | 0.0232 ± 0.0019 | 0.1471 ± 0.0057 |
| **Harmonic Oscillator** | Baseline SSM (RK4) | 0.0008 ± 0.0002 | 0.0028 ± 0.0005 | 0.0101 ± 0.0023 | 0.0055 ± 0.0005 |
| **Harmonic Oscillator** | Hamiltonian SSM (1-Step) | 0.0023 ± 0.0021 | 0.0080 ± 0.0054 | 0.0360 ± 0.0262 | 0.0092 ± 0.0022 |
| **Harmonic Oscillator** | Separable HNN (Multi-Step) | 0.0001 ± 0.0001 | 0.0002 ± 0.0002 | 0.0006 ± 0.0007 | 0.0006 ± 0.0002 |
| **Harmonic Oscillator** | Port-Hamiltonian SSM (Multi-Step) | 0.0014 ± 0.0003 | 0.0048 ± 0.0002 | 0.0193 ± 0.0006 | 0.1409 ± 0.0053 |
| **Damped Pendulum (Dissipative)** | Baseline SSM (RK4) | 0.0001 ± 0.0000 | 0.0001 ± 0.0001 | 0.0001 ± 0.0001 | 0.5639 ± 0.0052 |
| **Damped Pendulum (Dissipative)** | Hamiltonian SSM (1-Step) | 0.0299 ± 0.0010 | 0.1222 ± 0.0058 | 0.3523 ± 0.0377 | 0.0682 ± 0.0018 |
| **Damped Pendulum (Dissipative)** | Separable HNN (Multi-Step) | 0.0220 ± 0.0017 | 0.0935 ± 0.0066 | 0.2267 ± 0.0101 | 0.0177 ± 0.0011 |
| **Damped Pendulum (Dissipative)** | Port-Hamiltonian SSM (Multi-Step) | 0.0016 ± 0.0002 | 0.0048 ± 0.0011 | 0.0069 ± 0.0012 | 0.4685 ± 0.0142 |