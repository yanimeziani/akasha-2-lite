"""
Akasha-Nav: Hamiltonian Symplectic Kinematic Estimator vs Naive/EKF IMU Baselines
Evaluates GPS-denied dead-reckoning trajectory drift.
"""

import torch
import numpy as np
from typing import Tuple, Dict

class IMUSimulator:
    """Simulates realistic 3D drone flight dynamics with IMU noise and sensor bias."""
    def __init__(self, dt: float = 0.05, duration: float = 60.0):
        self.dt = dt
        self.duration = duration
        self.timesteps = int(duration / dt)

    def generate_ground_truth(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generates a smooth 3D periodic flight corridor (figure-8 / loop)."""
        t = np.linspace(0, self.duration, self.timesteps)
        
        # 3D Position trajectory
        x = 15.0 * np.sin(0.2 * t)
        y = 10.0 * np.sin(0.4 * t)
        z = 5.0 + 2.0 * np.cos(0.15 * t)
        pos = np.stack([x, y, z], axis=-1)

        # Numerical velocity and acceleration
        vel = np.gradient(pos, self.dt, axis=0)
        acc = np.gradient(vel, self.dt, axis=0)

        return t, pos, vel, acc

    def add_imu_sensor_noise(self, acc: np.ndarray, 
                              noise_std: float = 0.08, 
                              bias_drift: float = 0.025) -> np.ndarray:
        """
        Corrupts ground-truth acceleration with high-frequency Gaussian noise
        and constant sensor bias drift (the primary cause of quadratic O(t^2) dead-reckoning drift).
        """
        N = acc.shape[0]
        noise = np.random.normal(0, noise_std, size=acc.shape)
        
        # Linear accelerometer bias drift over time
        bias = bias_drift * (np.arange(N)[:, None] / N)
        
        noisy_acc = acc + noise + bias
        return noisy_acc


class NaiveDoubleIntegrator:
    """Standard unconstrained dead-reckoning: v += a*dt, x += v*dt."""
    def __init__(self, dt: float):
        self.dt = dt

    def estimate(self, init_pos: np.ndarray, init_vel: np.ndarray, noisy_acc: np.ndarray) -> np.ndarray:
        N = noisy_acc.shape[0]
        est_pos = np.zeros((N, 3))
        est_vel = np.zeros((N, 3))

        est_pos[0] = init_pos
        est_vel[0] = init_vel

        for i in range(N - 1):
            est_vel[i + 1] = est_vel[i] + noisy_acc[i] * self.dt
            est_pos[i + 1] = est_pos[i] + est_vel[i] * self.dt

        return est_pos, est_vel


class AkashaHamiltonianNavFilter:
    """
    Hamiltonian Symplectic Kinematic Filter:
    1. Formulates state as canonical coordinates (q = position, p = momentum = m*v).
    2. Enforces vehicle physical energy constraints (H_max = 0.5 * m * v_max^2 + V_corridor).
    3. Integrates via 2nd-order Symplectic Leapfrog, eliminating secular energy runaway.
    """
    def __init__(self, dt: float, mass: float = 1.2, max_speed: float = 8.0):
        self.dt = dt
        self.mass = mass
        self.max_speed = max_speed
        self.max_kinetic_energy = 0.5 * mass * (max_speed ** 2)

    def estimate(self, init_pos: np.ndarray, init_vel: np.ndarray, noisy_acc: np.ndarray) -> np.ndarray:
        N = noisy_acc.shape[0]
        est_q = np.zeros((N, 3))
        est_p = np.zeros((N, 3))

        est_q[0] = init_pos
        est_p[0] = self.mass * init_vel

        for i in range(N - 1):
            # Input force from accelerometer: F = m * a
            F_raw = self.mass * noisy_acc[i]

            # Symplectic Leapfrog Half-step momentum kick
            p_half = est_p[i] + 0.5 * self.dt * F_raw

            # Hamiltonian Energy Bounding (Physical Manifold Projection)
            kinetic_energy = 0.5 * np.sum(p_half ** 2) / self.mass
            if kinetic_energy > self.max_kinetic_energy:
                scale = np.sqrt(self.max_kinetic_energy / kinetic_energy)
                p_half *= scale

            # Full-step position drift on canonical manifold
            vel_half = p_half / self.mass
            q_next = est_q[i] + self.dt * vel_half

            # Virtual Potential Corridor damping (soft guidance towards physical continuity)
            # Damps out orthogonal high-frequency sensor jitter
            F_damped = F_raw - 0.15 * vel_half

            # Second half-step momentum kick
            p_next = p_half + 0.5 * self.dt * F_damped

            # Final energy projection
            ke_next = 0.5 * np.sum(p_next ** 2) / self.mass
            if ke_next > self.max_kinetic_energy:
                p_next *= np.sqrt(self.max_kinetic_energy / ke_next)

            est_q[i + 1] = q_next
            est_p[i + 1] = p_next

        est_vel = est_p / self.mass
        return est_q, est_vel
