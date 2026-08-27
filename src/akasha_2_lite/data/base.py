import abc
import numpy as np
import torch

class DynamicalSystem(abc.ABC):
    """Abstract base class for physical dynamical systems."""

    @abc.abstractmethod
    def hamiltonian(self, q: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
        """Compute the scalar Hamiltonian H(q, p)."""
        pass

    @abc.abstractmethod
    def equations_of_motion(self, t: float, state: np.ndarray) -> np.ndarray:
        """Compute state derivative d/dt [q, p] for numerical integration."""
        pass

    @abc.abstractmethod
    def sample_initial_conditions(self, n_samples: int, rng: np.random.Generator) -> np.ndarray:
        """Sample initial states [n_samples, state_dim]."""
        pass
