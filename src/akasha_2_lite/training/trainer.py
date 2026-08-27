import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from typing import Dict, Any, Tuple

def prepare_transition_loader(
    trajectories: torch.Tensor,
    batch_size: int = 128,
    shuffle: bool = True,
) -> DataLoader:
    """
    Given trajectories of shape [N, T, D], extracts consecutive pairs (x_t, x_{t+1})
    and packages them into a DataLoader.
    """
    # x_t: all steps except last
    x_t = trajectories[:, :-1, :].reshape(-1, trajectories.shape[-1])
    # x_next: all steps except first
    x_next = trajectories[:, 1:, :].reshape(-1, trajectories.shape[-1])

    dataset = TensorDataset(x_t, x_next)
    return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle)


def train_dynamical_model(
    model: nn.Module,
    train_loader: DataLoader,
    dt: float,
    epochs: int = 25,
    lr: float = 1e-3,
    weight_decay: float = 1e-5,
    device: str = "cpu",
) -> Dict[str, Any]:
    """
    Trains a dynamical model (Baseline or Hamiltonian) using 1-step MSE loss.
    """
    model.to(device)
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.MSELoss()

    loss_history = []

    for epoch in range(epochs):
        epoch_loss = 0.0
        n_batches = 0
        for x_t, x_next in train_loader:
            x_t = x_t.to(device)
            x_next = x_next.to(device)

            optimizer.zero_grad()
            pred_next = model.forward_step(x_t, dt)
            loss = criterion(pred_next, x_next)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        scheduler.step()
        avg_loss = epoch_loss / max(n_batches, 1)
        loss_history.append(avg_loss)

    model.eval()
    return {
        "final_train_loss": loss_history[-1],
        "loss_history": loss_history,
    }
