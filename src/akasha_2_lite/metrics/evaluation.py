import torch
import numpy as np
from typing import Dict, Any, Callable, Optional

def compute_rollout_metrics(
    pred_trajectories: torch.Tensor,
    true_trajectories: torch.Tensor,
    hamiltonian_fn: Optional[Callable[[torch.Tensor, torch.Tensor], torch.Tensor]] = None,
    eps: float = 1e-6,
) -> Dict[str, Any]:
    """
    Computes rollout accuracy and energy conservation metrics.

    Args:
        pred_trajectories: Tensor of shape [batch, time_steps, state_dim]
        true_trajectories: Tensor of shape [batch, time_steps, state_dim]
        hamiltonian_fn: Optional callable (q, p) -> energy for calculating Hamiltonian drift
        eps: Small constant to avoid division by zero in relative energy drift

    Returns:
        Dictionary containing:
            - mse_over_time: Array of shape [time_steps] (mean MSE at each rollout step)
            - mean_rollout_mse: Overall scalar MSE across all timesteps and batches
            - horizon_50_mse: MSE at step 50 (or closest available)
            - horizon_100_mse: MSE at step 100 (or closest available)
            - horizon_200_mse: MSE at step 200 (or closest available)
            - final_step_mse: MSE at the final rollout step
            - mean_h_drift: Mean relative Hamiltonian drift across rollout (if hamiltonian_fn given)
            - max_h_drift: Maximum relative Hamiltonian drift across rollout
            - h_drift_over_time: Array of shape [time_steps] tracking drift per step
    """
    assert pred_trajectories.shape == true_trajectories.shape, (
        f"Shape mismatch: {pred_trajectories.shape} vs {true_trajectories.shape}"
    )

    batch_size, time_steps, state_dim = pred_trajectories.shape

    # Squared error per step: [batch, time_steps, state_dim]
    sq_err = (pred_trajectories - true_trajectories) ** 2
    # Mean over state dimension, then mean over batch: [time_steps]
    mse_over_time = sq_err.mean(dim=-1).mean(dim=0).detach().cpu().numpy()
    mean_rollout_mse = float(mse_over_time.mean())

    metrics = {
        "mse_over_time": mse_over_time,
        "mean_rollout_mse": mean_rollout_mse,
        "final_step_mse": float(mse_over_time[-1]),
    }

    for step_target in [50, 100, 200]:
        if time_steps >= step_target:
            metrics[f"horizon_{step_target}_mse"] = float(mse_over_time[step_target - 1])

    if hamiltonian_fn is not None:
        # Assuming state is [..., 0] = q, [..., 1] = p
        q_pred = pred_trajectories[..., 0]
        p_pred = pred_trajectories[..., 1]
        h_pred = hamiltonian_fn(q_pred, p_pred) # [batch, time_steps]

        h0 = h_pred[:, 0:1] # [batch, 1]
        rel_drift = torch.abs(h_pred - h0) / (torch.abs(h0) + eps) # [batch, time_steps]

        drift_over_time = rel_drift.mean(dim=0).detach().cpu().numpy()
        metrics["h_drift_over_time"] = drift_over_time
        metrics["mean_h_drift"] = float(drift_over_time.mean())
        metrics["max_h_drift"] = float(drift_over_time.max())

    return metrics


def measure_model_efficiency(
    model: torch.nn.Module,
    sample_input: torch.Tensor,
    n_warmup: int = 10,
    n_runs: int = 50,
) -> Dict[str, Any]:
    """
    Measures parameter count, forward inference latency (ms), and peak memory.
    """
    import time

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    model.eval()
    with torch.no_grad():
        for _ in range(n_warmup):
            _ = model(sample_input)

        latencies = []
        for _ in range(n_runs):
            t0 = time.perf_counter()
            _ = model(sample_input)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0) # in ms

    return {
        "total_parameters": total_params,
        "trainable_parameters": trainable_params,
        "mean_latency_ms": float(np.mean(latencies)),
        "std_latency_ms": float(np.std(latencies)),
    }
