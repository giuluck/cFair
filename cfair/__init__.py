from typing import Union

from cfair.backends import Backend
from cfair.indicators import Indicator, DoubleKernelIndicator, SingleKernelIndicator, NeuralIndicator, \
    LatticeIndicator, DensityIndicator, RandomizedIndicator
from cfair.typing import BackendType, SemanticsType, AlgorithmType


def indicator(backend: Union[Backend, BackendType],
              semantics: SemanticsType,
              algorithm: AlgorithmType,
              **kwargs) -> Indicator:
    """Builds the instance of an indicator for continuous attributes using the given indicator semantics.

    :param backend:
        The backend to use, or its alias.

    :param semantics:
        The type of indicator semantics.

    :param algorithm:
        The computational algorithm used for computing the indicator.

    :param kwargs:
        Additional algorithm-specific arguments.
    """
    algorithm = algorithm.lower().replace('-', ' ').replace('_', ' ')
    if algorithm in ['dk', 'double kernel']:
        return DoubleKernelIndicator(backend=backend, semantics=semantics, **kwargs)
    elif algorithm in ['sk', 'single kernel']:
        return SingleKernelIndicator(backend=backend, semantics=semantics, **kwargs)
    elif algorithm in ['nn', 'neural']:
        return NeuralIndicator(backend=backend, semantics=semantics, **kwargs)
    elif algorithm in ['kde', 'density']:
        return DensityIndicator(backend=backend, semantics=semantics, **kwargs)
    elif algorithm in ['rdc', 'randomized']:
        return RandomizedIndicator(backend=backend, semantics=semantics, **kwargs)
    elif algorithm in ['lat', 'lattice']:
        return LatticeIndicator(backend=backend, semantics=semantics, **kwargs)
    else:
        raise AssertionError(f"Unsupported algorithm '{algorithm}'")


def hgr(backend: Union[Backend, BackendType], algorithm: AlgorithmType = 'dk', **kwargs) -> Indicator:
    """Builds a Hirschfield-Gebelin-Renyi (HGR) indicator instance.

    :param backend:
        The backend to use, or its alias.

    :param algorithm:
        The computational algorithm used for computing the indicator.

    :param kwargs:
        Additional algorithm-specific arguments.
    """
    return indicator(backend=backend, algorithm=algorithm, semantics='hgr', **kwargs)


def gedi(backend: Union[Backend, BackendType], algorithm: AlgorithmType = 'dk', **kwargs) -> Indicator:
    """Builds a Generalized Disparate Impact (GeDI) indicator instance.

    :param backend:
        The backend to use, or its alias.

    :param algorithm:
        The computational algorithm used for computing the indicator.

    :param kwargs:
        Additional algorithm-specific arguments.
    """
    return indicator(backend=backend, algorithm=algorithm, semantics='gedi', **kwargs)


def nlc(backend: Union[Backend, BackendType], algorithm: AlgorithmType = 'dk', **kwargs) -> Indicator:
    """Builds a Non-Linear Covariance (NLC) indicator instance.

    :param backend:
        The backend to use, or its alias.

    :param algorithm:
        The computational algorithm used for computing the indicator.

    :param kwargs:
        Additional algorithm-specific arguments.
    """
    return indicator(backend=backend, algorithm=algorithm, semantics='nlc', **kwargs)
