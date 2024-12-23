from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Union, Tuple, Dict

from cfair.backends import NumpyBackend, TorchBackend, Backend, TensorflowBackend
from cfair.typing import BackendType, SemanticsType


class Indicator:
    """Interface of a fairness indicator for continuous attributes.

    The definition of the indicators are based on three semantics obtained by projecting the input vectors into a
    non-linear mapping space. The first vector (a) is mapped into its projection (x) defined as:
        x = fa * std(a), where mean(fa) = 0 and std(fa) = 1
    while the second vector (b) is mapped into its projection (y) defined as:
        y = gb * std(b), where mean(gb) = 0 and std(gb) = 1

    By definition, projections (x, y) are centered and with standard deviation equal to the original vectors (a, b),
    while we also consider their standardized versions as <fa> and <gb>, respectively. At this point, the three
    semantics simply define three correlation indicators on <x> and <y>, specifically:

        - HGR is the Hirschfield-Gebelin-Renyi indicator, namely the Non-Linear Pearson's correlation. It is computed
          as the average of the product between the standardized projections without a scaling factor, in fact:
            pearson(x, y) = cov(x, y) / std(x) / std(y) =
                          = cov(x, y) / std(a) / std(b) =
                          = cov(fa * std(a), gb * std(b)) / std(a) / std(b) =
                          = cov(fa, gb) =
                          = mean(fa * gb)

        - GeDI is the Generalized Disparate Impact, namely the ration between the covariance of the two vectors and the
          variance of the first. Eventually, it can be computed as the average of the product between the standardized
          projections (HGR) multiplied by a scaling factor std(b) / std(a), in fact:
            cov(x, y) / var(x) = cov(x, y) / var(a) =
                               = cov(x, y) / std(a) / std(a) =
                               = cov(fa * std(a), gb * std(b)) / std(a) / std(a) =
                               = cov(fa, gb) * std(b) / std(a) =
                               = mean(fa * gb) * std(b) / std(a) =
                               = HGR(a, b) * std(b) / std(a)

        - NLC is the Non-Linear Covariance, which can be eventually computed as the average of the product between the
          standardized projections (HGR) multiplied by a scaling factor std(b) * std(a), in fact:
            cov(x, y) = cov(x, y) =
                      = cov(fa * std(a), gb * std(b)) =
                      = cov(fa, gb) * std(b) * std(a) =
                      = mean(fa * gb) * std(b) * std(a) =
                      = HGR(a, b) * std(b) * std(a)
    """

    @dataclass(frozen=True, init=True, repr=False, eq=False)
    class Result:
        """Data class representing the results of an indicator computation."""

        a: Any = field()
        """The first of the two vectors on which the indicator is computed."""

        b: Any = field()
        """The first of the two vectors on which the indicator is computed."""

        value: Any = field()
        """The value measured by the indicator, optionally with gradient information attached."""

        indicator: Any = field()
        """The indicator instance that generated this result."""

        num_call: int = field()
        """The n-th time at which the indicator instance that generated the result was called."""

    def __init__(self, backend: Union[Backend, BackendType], semantics: SemanticsType):
        """
        :param backend:
            The backend to use to compute the indicator, or its alias.

        :param semantics:
            The semantics of the indicator ('hgr', 'gedi', or 'nlc').
        """
        # handle backend
        backend = backend.lower()
        if backend == 'numpy':
            backend = NumpyBackend()
        elif backend == 'tensorflow':
            backend = TensorflowBackend()
        elif backend == 'torch':
            backend = TorchBackend()
        elif not isinstance(backend, Backend):
            raise ValueError(f"Unknown backend '{backend}'")
        # handle semantics
        semantics = semantics.lower()
        if semantics == 'hgr':
            factor = lambda a, b: 1
        elif semantics == 'gedi':
            factor = lambda a, b: self.backend.std(b) / self.backend.std(a)
        elif semantics == 'nlc':
            factor = lambda a, b: self.backend.std(b) * self.backend.std(a)
        else:
            raise ValueError(f"Unknown semantics '{semantics}'")
        # noinspection PyTypeChecker
        self._backend: Backend = backend
        self._factor: Callable[[Any, Any], Any] = factor
        self._last_result: Optional[Indicator.Result] = None
        self._num_calls: int = 0

    @property
    def backend(self) -> Backend:
        """The backend to use to compute the indicator."""
        return self._backend

    @property
    def last_result(self) -> Optional[Result]:
        """The `Result` instance returned from the last indicator call, or None if no call was performed."""
        return self._last_result

    @property
    def num_calls(self) -> int:
        """The number of times that this indicator instance was called."""
        return self._num_calls

    def compute(self, a, b) -> Any:
        """Computes the indicator.

        :param a:
            The first vector.

        :param b:
            The second vector.

        :result:
            A scalar value representing the computed indicator value, optionally with gradient information attached."""
        return self(a=a, b=b).value

    def __call__(self, a, b) -> Any:
        """Computes the indicator.

        :param a:
            The first vector.

        :param b:
            The second vector.

        :result:
            A `Result` instance containing the computed indicator value together with additional information.
        """
        bk = self.backend
        assert bk.ndim(a) == bk.ndim(b) == 1, f"Expected vectors with one dimension, got {bk.ndim(a)} and {bk.ndim(b)}"
        assert bk.len(a) == bk.len(b), f"Input vectors must have the same dimension, got {bk.len(a)} != {bk.len(b)}"
        self._num_calls += 1
        value, kwargs = self._value(a=bk.cast(a, dtype=float), b=bk.cast(b, dtype=float))
        # noinspection PyArgumentList
        result = self.Result(
            a=a,
            b=b,
            value=value * self._factor(a, b),
            num_call=self.num_calls,
            indicator=self,
            **kwargs
        )
        self._last_result = result
        return result

    @abstractmethod
    def _value(self, a, b) -> Tuple[Any, Dict[str, Any]]:
        """Computes the value of the indicator.

        :param a:
            The first vector.

        :param b:
            The second vector.

        :result:
            A tuple <value, kwargs> containing the value of the indicator along with optional additional results.
        """
        pass


class CopulaIndicator(Indicator):
    """Interface of a fairness indicator for continuous attributes using copula transformations."""

    def __init__(self, backend: Union[Backend, BackendType], semantics: SemanticsType, eps: float):
        """
        :param backend:
            The backend to use to compute the indicator, or its alias.

        :param semantics:
            The semantics of the indicator.

        :param eps:
            The epsilon value used to avoid division by zero in case of null standard deviation.
        """
        super(CopulaIndicator, self).__init__(backend=backend, semantics=semantics)
        self._eps: float = eps

    @property
    def eps(self) -> float:
        """The epsilon value used to avoid division by zero in case of null standard deviation."""
        return self._eps

    @abstractmethod
    def _f(self, a) -> Any:
        pass

    @abstractmethod
    def _g(self, b) -> Any:
        pass

    def f(self, a) -> Any:
        """Returns the mapped vector f(a) using the copula transformation f computed in the last execution.

        :param a:
            The vector to be projected.

        :return:
            The resulting projection with zero mean and unitary variance.
        """
        assert self.last_result is not None, "The indicator has not been computed yet, no transformation can be used."
        return self._f(a)

    def g(self, b) -> Any:
        """Returns the mapped vector g(b) using the copula transformation g computed in the last execution.

        :param b:
            The vector to be projected.

        :return:
            The resulting projection with zero mean and unitary variance.
        """
        assert self.last_result is not None, "The indicator has not been computed yet, no transformation can be used."
        return self._g(b)

    def value(self, a, b) -> float:
        """Gets the indicator value using the stored copula transformations on the two given vectors.

        :param a:
            The first vector.

        :param b:
            The second vector.

        :return:
            The computed indicator.
        """
        assert self.last_result is not None, "The indicator has not been computed yet, no transformation can be used."
        fa = self.backend.standardize(self._f(a=a), eps=self.eps)
        gb = self.backend.standardize(self._g(b=b), eps=self.eps)
        value = self.backend.mean(fa * gb) * self._factor(a=a, b=b)
        return self.backend.item(value)
