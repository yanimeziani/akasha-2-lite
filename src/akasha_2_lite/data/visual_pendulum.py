import numpy as np
import torch
from akasha_2_lite.data.pendulum import IdealPendulum

def render_pendulum_frame(q: float, img_size: int = 64) -> np.ndarray:
    """
    Renders a single 64x64 grayscale anti-aliased frame of a pendulum at angle q.
    Pivot: (cx, cy) = (32, 16). Length L = 26 px. Bob radius R = 4 px.
    """
    img = np.zeros((img_size, img_size), dtype=np.float32)
    cx, cy = img_size // 2, img_size // 4
    L = 24.0

    # Bob center
    bx = cx + L * np.sin(q)
    by = cy + L * np.cos(q)

    # Grid coordinates
    y_coords, x_coords = np.ogrid[:img_size, :img_size]

    # 1. Render circular bob
    dist_sq_bob = (x_coords - bx) ** 2 + (y_coords - by) ** 2
    bob_mask = np.clip(1.0 - (np.sqrt(dist_sq_bob) - 3.5), 0.0, 1.0)

    # 2. Render rod line segment from (cx, cy) to (bx, by)
    dx = bx - cx
    dy = by - cy
    length_sq = dx * dx + dy * dy
    if length_sq > 0:
        t = np.clip(((x_coords - cx) * dx + (y_coords - cy) * dy) / length_sq, 0.0, 1.0)
        proj_x = cx + t * dx
        proj_y = cy + t * dy
        dist_sq_rod = (x_coords - proj_x) ** 2 + (y_coords - proj_y) ** 2
        rod_mask = np.clip(1.0 - (np.sqrt(dist_sq_rod) - 0.8), 0.0, 1.0) * 0.7
    else:
        rod_mask = np.zeros_like(img)

    # Pivot dot
    dist_sq_pivot = (x_coords - cx) ** 2 + (y_coords - cy) ** 2
    pivot_mask = np.clip(1.0 - (np.sqrt(dist_sq_pivot) - 2.0), 0.0, 1.0) * 0.9

    img = np.maximum(np.maximum(bob_mask, rod_mask), pivot_mask)
    return img.astype(np.float32)


def generate_visual_pendulum_dataset(
    n_trajectories: int = 150,
    n_steps: int = 40,
    dt: float = 0.05,
    img_size: int = 64,
    seed: int = 42,
) -> torch.Tensor:
    """
    Generates synthetic video trajectories of shape [N, T, 1, H, W].
    """
    pendulum = IdealPendulum(g=3.0)
    trajs, _ = pendulum.generate_trajectories(
        n_trajectories=n_trajectories, n_steps=n_steps, dt=dt, seed=seed
    )
    # trajs shape: [N, T, 2] where trajs[..., 0] is angle q

    dataset = np.zeros((n_trajectories, n_steps, 1, img_size, img_size), dtype=np.float32)

    for i in range(n_trajectories):
        for t in range(n_steps):
            q_val = float(trajs[i, t, 0].item())
            dataset[i, t, 0] = render_pendulum_frame(q_val, img_size=img_size)

    return torch.from_numpy(dataset)
