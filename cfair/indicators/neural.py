"""
HGR implementation of the method from "Fairness-Aware Neural Renyi Minimization for Continuous Features" by Vincent
Grari, Sylvain Lamprier and Marcin Detyniecki. The code has been partially taken and reworked from the repository
containing the code of the paper: https://github.com/fairml-research/HGR_NN/tree/main.
"""
import importlib.util
from abc import ABC
from typing import Any, Union, Iterable, Optional, Tuple, Callable

from cfair.backends import Backend, NumpyBackend, TorchBackend, TensorflowBackend
from cfair.indicators.indicator import CopulaIndicator, HGRIndicator, GeDIIndicator, NLCIndicator


class NeuralIndicator(CopulaIndicator, ABC):
    """Fairness indicator computed using two neural networks to approximate the copula transformations."""

    def __init__(self,
                 f_units: Optional[Iterable[int]] = (16, 16, 8),
                 g_units: Optional[Iterable[int]] = (16, 16, 8),
                 backend: Union[str, Backend] = 'numpy',
                 epochs_start: int = 1000,
                 epochs_successive: Optional[int] = 50,
                 eps: float = 1e-9):
        """
        :param backend:
            The backend to use to compute the indicator, or its alias.

        :param f_units:
            The hidden units of the F copula network, or None for no F copula network.

        :param g_units:
            The hidden units of the G copula network, or None for no G copula network.

        :param epochs_start:
            The number of training epochs in the first call.

        :param epochs_successive:
            The number of training epochs in the subsequent calls (fine-tuning of the pre-trained networks).

        :param eps:
            The epsilon value used to avoid division by zero in case of null standard deviation.
        """
        assert f_units is not None or g_units is not None, "Either f_units or g_units must not be None"
        super(NeuralIndicator, self).__init__(backend=backend, eps=eps)
        # use default backend if it has a neural engine, otherwise prioritize torch and then tensorflow
        if isinstance(self.backend, TensorflowBackend):
            build_fn = self._build_tensorflow
            train_fn = self._train_tensorflow
            neural_backend = self.backend
        elif isinstance(self.backend, TorchBackend) or importlib.util.find_spec('torch') is not None:
            build_fn = self._build_torch
            train_fn = self._train_torch
            neural_backend = TorchBackend()
        elif importlib.util.find_spec('tensorflow') is not None:
            build_fn = self._build_tensorflow
            train_fn = self._train_tensorflow
            neural_backend = TensorflowBackend()
        elif isinstance(self.backend, NumpyBackend):
            raise ModuleNotFoundError(
                "NeuralHGR relies on neural networks and needs either pytorch or tensorflow installed even if "
                "NumpyBackend() is selected. Please install it via 'pip install torch' or 'pip install tensorflow'"
            )
        else:
            raise AssertionError(f"Unsupported backend f'{self.backend}")

        self._unitsF: Optional[Tuple[int]] = None if f_units is None else tuple(f_units)
        self._unitsG: Optional[Tuple[int]] = None if g_units is None else tuple(g_units)
        self._epochs_start: int = epochs_start
        self._epochs_successive: int = epochs_successive
        self._neural_backend: Backend = neural_backend
        self._train_fn: Callable[[Any, Any], None] = train_fn
        self._netF, self._optF = build_fn(units=self.f_units)
        self._netG, self._optG = build_fn(units=self.g_units)

    @property
    def f_units(self) -> Optional[Tuple[int]]:
        """The hidden units of the F copula network, or None if no F copula network."""
        return self._unitsF

    @property
    def g_units(self) -> Optional[Tuple[int]]:
        """The hidden units of the G copula network, or None if no G copula network."""
        return self._unitsG

    @property
    def epochs_start(self) -> int:
        """The number of training epochs in the first call."""
        return self._epochs_start

    @property
    def epochs_successive(self) -> int:
        """The number of training epochs in the subsequent calls (fine-tuning of the pre-trained networks)."""
        return self._epochs_successive

    def _f(self, a) -> Any:
        a = self._neural_backend.cast(a, dtype=float)
        a = self._neural_backend.reshape(a, shape=(-1, 1))
        fa = self._netF(a)
        fa = self._neural_backend.reshape(fa, shape=-1)
        return self._neural_backend.numpy(fa) if isinstance(self.backend, NumpyBackend) else fa

    def _g(self, b) -> Any:
        b = self._neural_backend.cast(b, dtype=float)
        b = self._neural_backend.reshape(b, shape=(-1, 1))
        gb = self._netG(b)
        gb = self._neural_backend.reshape(gb, shape=-1)
        return self._neural_backend.numpy(gb) if isinstance(self.backend, NumpyBackend) else gb

    def _compute(self, a, b) -> CopulaIndicator.Result:
        # cast the vectors to the neural backend type
        a_cast = self._neural_backend.reshape(self._neural_backend.cast(a, dtype=float), shape=(-1, 1))
        b_cast = self._neural_backend.reshape(self._neural_backend.cast(b, dtype=float), shape=(-1, 1))
        for _ in range(self._epochs_start if self.num_calls == 0 else self._epochs_successive):
            self._train_fn(a_cast, b_cast)
        # compute the indicator value as the absolute value of the (mean) vector product
        # (since vectors are standardized) multiplied by the scaling factor
        value = self._hgr(a=a_cast, b=b_cast) * self._factor(a=a, b=b)
        value = self._neural_backend.item(value) if isinstance(self.backend, NumpyBackend) else value
        # return the result instance
        return NeuralIndicator.Result(
            a=a,
            b=b,
            value=value,
            num_call=self.num_calls,
            indicator=self
        )

    class _DummyNetwork:
        def __call__(self, x):
            return x

        @property
        def trainable_weights(self) -> list:
            return []

    class _DummyOptimizer:
        def zero_grad(self):
            return

        def step(self):
            return

        def apply_gradients(self, g):
            return

    def _hgr(self, a, b) -> Any:
        fa = self._neural_backend.standardize(self._netF(a), eps=self.eps)
        gb = self._neural_backend.standardize(self._netG(b), eps=self.eps)
        return self._neural_backend.mean(fa * gb)

    @staticmethod
    def _build_torch(units: Optional[Tuple[int]]) -> tuple:
        import torch
        if units is None:
            network = NeuralIndicator._DummyNetwork()
            optimizer = NeuralIndicator._DummyOptimizer()
        else:
            layers = []
            for inp, out in zip([1, *units], [*units, 1]):
                layers += [torch.nn.Linear(inp, out), torch.nn.ReLU()]
            network = torch.nn.Sequential(*layers[:-1])
            optimizer = torch.optim.Adam(network.parameters(), lr=0.0005)
        return network, optimizer

    def _train_torch(self, a, b) -> None:
        self._optF.zero_grad()
        self._optG.zero_grad()
        loss = -self._hgr(a, b)
        loss.backward()
        self._optF.step()
        self._optG.step()

    @staticmethod
    def _build_tensorflow(units: Optional[Tuple[int]]) -> tuple:
        import tensorflow as tf
        if units is None:
            network = NeuralIndicator._DummyNetwork()
            optimizer = NeuralIndicator._DummyOptimizer()
        else:
            layers = [tf.keras.layers.Dense(out, activation='relu') for out in units]
            layers = [*layers, tf.keras.layers.Dense(1)]
            network = tf.keras.Sequential(layers)
            optimizer = tf.keras.optimizers.Adam(learning_rate=0.0005)
        return network, optimizer

    def _train_tensorflow(self, a, b) -> None:
        import tensorflow as tf
        with tf.GradientTape(persistent=True) as tape:
            loss = -self._hgr(a, b)
        f_grads = tape.gradient(loss, self._netF.trainable_weights)
        g_grads = tape.gradient(loss, self._netG.trainable_weights)
        self._optF.apply_gradients(zip(f_grads, self._netF.trainable_weights))
        self._optG.apply_gradients(zip(g_grads, self._netG.trainable_weights))


class NeuralHGR(NeuralIndicator, HGRIndicator):
    """Hirschfield-Gebelin-Renyi coefficient using two neural networks to approximate the copula transformations."""
    pass


class NeuralGeDI(NeuralIndicator, GeDIIndicator):
    """Generalized Disparate Impact using two neural networks to approximate the copula transformations."""
    pass


class NeuralNLC(NeuralIndicator, NLCIndicator):
    """Non-Linear Covariance computed two neural networks to approximate the copula transformations."""
    pass
