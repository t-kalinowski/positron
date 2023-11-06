#
# Copyright (C) 2023 Posit Software, PBC. All rights reserved.
#

from __future__ import annotations

import asyncio
import datetime
import inspect
import json
import math
import pprint
import random
import string
import sys
import types
from typing import Any, List, Set, Type, TypeVar, cast, Callable, Iterable, Optional, Tuple

import comm
import numpy as np
import pandas as pd
import polars as pl
import pytest
import torch
from fastcore.foundation import L
from IPython.terminal.interactiveshell import TerminalInteractiveShell

from positron import (
    PRINT_WIDTH,
    TRUNCATE_AT,
    EnvironmentService,
    EnvironmentVariable,
    EnvironmentVariableValueKind,
)
from positron.environment import _summarize_variable
from positron.inspectors import decode_access_key, encode_access_key, get_inspector
from positron.positron_ipkernel import PositronIPyKernel
from positron.utils import get_qualname

from .conftest import DummyComm


@pytest.fixture
def env_service(
    kernel: PositronIPyKernel,
) -> Iterable[EnvironmentService]:
    """
    A Positron environment service with an open comm.
    """
    env_service = kernel.env_service

    # Close any existing comm
    if env_service._comm is not None:
        env_service._comm.close()
        env_service._comm = None

    # Open a comm
    env_comm = cast(DummyComm, comm.create_comm("positron.environment"))
    open_msg = {}
    env_service.on_comm_open(env_comm, open_msg)

    # Clear messages due to the comm_open
    env_comm.messages.clear()

    yield env_service

    # Close the comm
    env_comm.close()
    env_service._comm = None


@pytest.fixture
def env_comm(env_service: EnvironmentService) -> DummyComm:
    """
    Convenience fixture for accessing the environment comm.
    """
    return cast(DummyComm, env_service._comm)


#
# Helpers
#


# Exclude the following fields by default:
# - size: since it depends on platform, Python version, and library versions.
# - access_key: since we test it independently from summarizing EnvironmentVariables and don't want
#               to have to change all tests when we change the access_key format.
def assert_environment_variable_equal(
    result: Optional[EnvironmentVariable],
    expected: EnvironmentVariable,
    exclude: Set[str] = {"size", "access_key"},
) -> None:
    assert result is not None

    result_dict = result.dict(exclude=exclude)
    expected_dict = expected.dict(exclude=exclude)

    assert result_dict == expected_dict


def assert_environment_variables_equal(
    result: List[EnvironmentVariable], expected: List[EnvironmentVariable]
) -> None:
    assert len(result) == len(expected)

    for result_item, expected_item in zip(result, expected):
        assert_environment_variable_equal(result_item, expected_item)


T = TypeVar("T")


def not_none(obj: Optional[T]) -> T:
    assert obj is not None
    return obj


class Ignore:
    """
    An object that's equal to every other object.
    """

    def __eq__(self, other: Any) -> bool:
        return True


IGNORE = Ignore()


class HelperClass:
    """
    A helper class for testing method functions.
    """

    def fn_no_args(self):
        return "No args"

    def fn_one_arg(self, x: str) -> str:
        return f"One arg {x}"

    def fn_two_args(self, x: int, y: int) -> Tuple[int, int]:
        return (x, y)


#
# Test Booleans
#

BOOL_CASES = [True, False]


@pytest.mark.parametrize("case", BOOL_CASES)
def test_summarize_boolean(case: bool) -> None:
    display_name = "xBool"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case),
        kind=EnvironmentVariableValueKind.boolean,
        display_type="bool",
        type_info="bool",
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


#
# Test Strings
#

STRING_CASES = [
    "",  # Empty String
    "Hello, world!",  # Basic String
    "    ",  # Whitespace String
    "First\nSecond\nThird",  # Multiline String
    "This has a Windows linebreak\r\n",  # Windows Linebreak
    " Space Before\tTab Between\tSpace After ",  # Trailing Whitespace
    "É una bella città",  # Accented String
    "こんにちは",  # Japanese String
    "עֶמֶק",  # RTL String
    "ʇxǝʇ",  # Upsidedown String
    "😅😁",  # Emoji String
]


@pytest.mark.parametrize("case", STRING_CASES)
def test_summarize_string(case: str) -> None:
    display_name = "xStr"
    length = len(case)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=repr(case),
        kind=EnvironmentVariableValueKind.string,
        display_type="str",
        type_info="str",
        length=length,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_string_truncated() -> None:
    display_name = "xStrT"
    long_string = "".join(random.choices(string.ascii_letters, k=(TRUNCATE_AT + 10)))
    length = len(long_string)
    expected_value = f"'{long_string[:TRUNCATE_AT]}'"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value,
        kind=EnvironmentVariableValueKind.string,
        display_type="str",
        type_info="str",
        length=length,
        is_truncated=True,
    )

    result = _summarize_variable(display_name, long_string)

    assert_environment_variable_equal(result, expected)


#
# Test Numbers
#

# Python 3 ints are unbounded, but we include a few large numbers
# for basic test cases
INT_CASES = [-sys.maxsize * 100, -sys.maxsize, -1, 0, 1, sys.maxsize, sys.maxsize * 100]


@pytest.mark.parametrize("case", INT_CASES)
def test_summarize_integer(case: int) -> None:
    display_name = "xInt"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case),
        kind=EnvironmentVariableValueKind.number,
        display_type="int",
        type_info="int",
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


NUMPY_SCALAR_CASES = [
    np.int8(1),
    np.int16(1),
    np.int32(1),
    np.int64(1),
    np.float16(1.0),
    np.float32(1.0),
    np.float64(1.0),
]


@pytest.mark.parametrize("case", NUMPY_SCALAR_CASES)
def test_summarize_numpy_scalars(case: np.integer) -> None:
    display_name = "xNumpyInt"
    dtype = str(case.dtype)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case),
        kind=EnvironmentVariableValueKind.number,
        display_type=str(dtype),
        type_info=f"numpy.{dtype}",
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


FLOAT_CASES = [
    float("-inf"),
    -sys.float_info.max,
    -1.0,
    -sys.float_info.min,
    float("nan"),
    0.0,
    sys.float_info.min,
    1.0,
    math.pi,
    sys.float_info.max,
    float("inf"),
]


@pytest.mark.parametrize("case", FLOAT_CASES)
def test_summarize_float(case: float) -> None:
    display_name = "xFloat"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case),
        kind=EnvironmentVariableValueKind.number,
        display_type="float",
        type_info="float",
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


COMPLEX_CASES = [
    complex(-1.0, 100.1),
    complex(-1.0, 0.0),
    complex(0, 0),
    complex(1.0, 0.0),
    complex(1.0, 100.1),
]


@pytest.mark.parametrize("case", COMPLEX_CASES)
def test_summarize_complex(case: complex) -> None:
    display_name = "xComplex"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case),
        kind=EnvironmentVariableValueKind.number,
        display_type="complex",
        type_info="complex",
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


#
# Test Bytes
#

BYTES_CASES = [b"", b"\x00", b"caff\\xe8"]


@pytest.mark.parametrize("case", BYTES_CASES)
def test_summarize_bytes(case: bytes) -> None:
    display_name = "xBytes"
    length = len(case)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case),
        kind=EnvironmentVariableValueKind.bytes,
        display_type=f"bytes [{length}]",
        type_info="bytes",
        length=length,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


BYTEARRAY_CASES = [bytearray(), bytearray(0), bytearray(1), bytearray(b"\x41\x42\x43")]


@pytest.mark.parametrize("case", BYTEARRAY_CASES)
def test_summarize_bytearray(case: bytearray) -> None:
    display_name = "xBytearray"
    length = len(case)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case),
        kind=EnvironmentVariableValueKind.bytes,
        display_type=f"bytearray [{length}]",
        type_info="bytearray",
        length=length,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_bytearray_truncated() -> None:
    display_name = "xBytearrayT"
    case = bytearray(TRUNCATE_AT * 2)
    length = len(case)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case)[:TRUNCATE_AT],
        kind=EnvironmentVariableValueKind.bytes,
        display_type=f"bytearray [{length}]",
        type_info="bytearray",
        length=length,
        is_truncated=True,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_memoryview() -> None:
    display_name = "xMemoryview"
    byte_array = bytearray("東京", "utf-8")
    case = memoryview(byte_array)
    length = len(case)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=str(case),
        kind=EnvironmentVariableValueKind.bytes,
        display_type=f"memoryview [{length}]",
        type_info="memoryview",
        length=length,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


TIMESTAMP_CASES = [pd.Timestamp("2021-01-01 01:23:45"), datetime.datetime(2021, 1, 1, 1, 23, 45)]


@pytest.mark.parametrize("case", TIMESTAMP_CASES)
def test_summarize_timestamp(case: datetime.datetime) -> None:
    display_name = "xTimestamp"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=repr(case),
        kind=EnvironmentVariableValueKind.other,
        # TODO: Split these tests so we don't have to use type() and get_qualname()?
        display_type=type(case).__name__,
        type_info=get_qualname(case),
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


#
# Test Empty
#

NONE_CASES = [None]


@pytest.mark.parametrize("case", NONE_CASES)
def test_summarize_none(case: None) -> None:
    display_name = "xNone"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value="None",
        kind=EnvironmentVariableValueKind.empty,
        display_type="NoneType",
        type_info="NoneType",
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


#
# Test Collections
#

SET_CASES = [
    set(),
    set([None]),
    set(BOOL_CASES),
    set(INT_CASES),
    set(FLOAT_CASES),
    set(COMPLEX_CASES),
    set(BYTES_CASES),
    set(STRING_CASES),
]


@pytest.mark.parametrize("case", SET_CASES)
def test_summarize_set(case: set) -> None:
    display_name = "xSet"
    length = len(case)
    expected_value = pprint.pformat(case, width=PRINT_WIDTH, compact=True)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value,
        kind=EnvironmentVariableValueKind.collection,
        display_type=f"set {{{length}}}",
        type_info="set",
        length=length,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_set_truncated() -> None:
    display_name = "xSetT"
    case = set(list(range(TRUNCATE_AT * 2)))
    length = len(case)
    expected_value = pprint.pformat(case, width=PRINT_WIDTH, compact=True)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value[:TRUNCATE_AT],
        kind=EnvironmentVariableValueKind.collection,
        display_type=f"set {{{length}}}",
        type_info="set",
        length=length,
        is_truncated=True,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


LIST_CASES = [
    [],
    NONE_CASES,
    BOOL_CASES,
    INT_CASES,
    FLOAT_CASES,
    COMPLEX_CASES,
    BYTES_CASES,
    BYTEARRAY_CASES,
    STRING_CASES,
]


@pytest.mark.parametrize("case", LIST_CASES)
def test_summarize_list(case: list) -> None:
    display_name = "xList"
    length = len(case)
    expected_value = pprint.pformat(case, width=PRINT_WIDTH, compact=True)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value,
        kind=EnvironmentVariableValueKind.collection,
        display_type=f"list [{length}]",
        type_info="list",
        length=length,
        has_children=length > 0,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_list_truncated() -> None:
    display_name = "xListT"
    case = list(range(TRUNCATE_AT * 2))
    length = len(case)
    expected_value = pprint.pformat(case, width=PRINT_WIDTH, compact=True)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value[:TRUNCATE_AT],
        kind=EnvironmentVariableValueKind.collection,
        display_type=f"list [{length}]",
        type_info="list",
        length=length,
        has_children=True,
        is_truncated=True,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_list_cycle() -> None:
    display_name = "xListCycle"
    case = list([1, 2])
    case.append(case)  # type: ignore
    length = len(case)
    expected_value = pprint.pformat(case, width=PRINT_WIDTH, compact=True)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value[:TRUNCATE_AT],
        kind=EnvironmentVariableValueKind.collection,
        display_type=f"list [{length}]",
        type_info="list",
        length=length,
        has_children=True,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


RANGE_CASES = [
    range(0),  # Empty Range
    range(1),  # Range with positive start, 1 element
    range(-1, 0),  # Range with negative start, 1 element
    range(-2, 3),  # Range with negative start, positive stop
    range(10, 21, 2),  # Range with positive start, positive stop, and positive step
    range(20, 9, -2),  # Range with positive start, positive stop, and negative step
    range(2, -10, -2),  # Range with positive start, negative stop, and negative step
    range(-20, -9, 2),  # Range with negative start, negative stop, and positive step
    range(-10, 3, 2),  # Range with negative start, positive stop, and positive step
    range(1, 5000),  # Large Range (compact display, does not show elements)
]


@pytest.mark.parametrize("case", RANGE_CASES)
def test_summarize_range(case: range) -> None:
    display_name = "xRange"
    length = len(case)
    expected_value = pprint.pformat(case, width=PRINT_WIDTH, compact=True)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value,
        kind=EnvironmentVariableValueKind.collection,
        display_type=f"range [{length}]",
        type_info="range",
        length=length,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


FASTCORE_LIST_CASES = [
    L(),
    L(NONE_CASES),
    L(BOOL_CASES),
    L(INT_CASES),
    L(FLOAT_CASES),
    L(COMPLEX_CASES),
    L(BYTES_CASES),
    L(BYTEARRAY_CASES),
    L(STRING_CASES),
]


@pytest.mark.parametrize("case", FASTCORE_LIST_CASES)
def test_summarize_fastcore_list(case: L) -> None:
    display_name = "xFastcoreList"
    length = len(case)
    expected_value = pprint.pformat(case, width=PRINT_WIDTH, compact=True)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value,
        kind=EnvironmentVariableValueKind.collection,
        display_type=f"L [{length}]",
        type_info="fastcore.foundation.L",
        length=length,
        has_children=length > 0,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


#
# Test Maps
#


MAP_CASES = [
    {},  # empty dict
    {"": None},  # empty key
    {10: "Ten"},  # int key
    {"A": True},  # bool value
    {"B": 1},  # int value
    {"C": -1.01},  # float value
    {"D": complex(1, 2)},  # complex value
    {"E": "Echo"},  # str value
    {"F": b"Foxtrot"},  # bytes value
    {"G": bytearray(b"\x41\x42\x43")},  # byterray value
    {"H": (1, 2, 3)},  # tuple value
    {"I": [1, 2, 3]},  # list value
    {"J": {1, 2, 3}},  # set value
    {"K": range(3)},  # range value
    {"L": {"L1": 1, "L2": 2, "L3": 3}},  # nested dict value
]


@pytest.mark.parametrize("case", MAP_CASES)
def test_summarize_map(case: dict) -> None:
    display_name = "xDict"
    length = len(case)
    expected_value = pprint.pformat(case, width=PRINT_WIDTH, compact=True)
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value,
        kind=EnvironmentVariableValueKind.map,
        display_type=f"dict [{length}]",
        type_info="dict",
        length=length,
        has_children=length > 0,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


#
# Test Functions
#
helper = HelperClass()


FUNCTION_CASES = [
    lambda: None,  # No argument lambda function
    lambda x: x,  # Single argument lambda function
    lambda x, y: x + y,  # Multiple argument lambda function
    helper.fn_no_args,  # No argument method
    helper.fn_one_arg,  # Single argument method with single return type
    helper.fn_two_args,  # Multiple argument method with tuple return type
]


@pytest.mark.parametrize("case", FUNCTION_CASES)
def test_summarize_function(case: Callable) -> None:
    display_name = "xFn"
    expected_value = f"{case.__qualname__}{inspect.signature(case)}"
    expected_type = "function"
    if isinstance(case, types.MethodType):
        expected_type = "method"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=expected_value,
        kind=EnvironmentVariableValueKind.function,
        display_type=expected_type,
        type_info=expected_type,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


#
# Test arrays
#


@pytest.mark.parametrize(
    "case",
    [
        np.array([1, 2, 3], dtype=np.int64),  # 1D
        np.array([[1, 2, 3], [4, 5, 6]], dtype=np.int64),  # 2D
    ],
)
def test_summarize_numpy_array(case: np.ndarray) -> None:
    display_name = "xNumpyArray"
    shape = case.shape
    display_shape = f"({shape[0]})" if len(shape) == 1 else str(tuple(shape))
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=np.array2string(case, separator=","),
        kind=EnvironmentVariableValueKind.collection,
        display_type=f"numpy.int64 {display_shape}",
        type_info="numpy.ndarray",
        has_children=True,
        is_truncated=True,
        length=shape[0],
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


@pytest.mark.parametrize(
    "case",
    [
        np.array(1, dtype=np.int64),
    ],
)
def test_summarize_numpy_array_0d(case: np.ndarray) -> None:
    display_name = "xNumpyArray0d"
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=np.array2string(case, separator=","),
        kind=EnvironmentVariableValueKind.number,
        display_type=f"numpy.int64",
        type_info="numpy.ndarray",
        has_children=False,
        is_truncated=True,
        length=0,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_children_numpy_array() -> None:
    case = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.int64)

    inspector = get_inspector(case)
    summary = inspector.summarize_children(case, _summarize_variable)

    assert_environment_variables_equal(
        summary,
        [
            not_none(_summarize_variable(0, case[0])),
            not_none(_summarize_variable(1, case[1])),
        ],
    )


#
# Test tables
#


def test_summarize_pandas_dataframe() -> None:
    case = pd.DataFrame({"a": [1, 2], "b": ["3", "4"]})

    display_name = "xPandasDataFrame"
    rows, cols = case.shape
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=f"[{rows} rows x {cols} columns] pandas.core.frame.DataFrame",
        kind=EnvironmentVariableValueKind.table,
        display_type=f"DataFrame [{rows}x{cols}]",
        type_info="pandas.core.frame.DataFrame",
        has_children=True,
        has_viewer=True,
        is_truncated=True,
        length=rows,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_children_pandas_dataframe() -> None:
    case = pd.DataFrame({"a": [1, 2], "b": ["3", "4"]})

    inspector = get_inspector(case)
    summary = inspector.summarize_children(case, _summarize_variable)

    assert_environment_variables_equal(
        summary,
        [
            not_none(_summarize_variable("a", case["a"])),
            not_none(_summarize_variable("b", case["b"])),
        ],
    )


def test_summarize_pandas_series() -> None:
    case = pd.Series({"a": 0, "b": 1})

    display_name = "xPandasSeries"
    (rows,) = case.shape
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value="[0, 1]",
        kind=EnvironmentVariableValueKind.map,
        display_type=f"int64 [{rows}]",
        type_info="pandas.core.series.Series",
        has_children=True,
        is_truncated=True,
        length=rows,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_polars_dataframe() -> None:
    case = pl.DataFrame({"a": [1, 2], "b": [3, 4]})

    display_name = "xPolarsDataFrame"
    rows, cols = case.shape
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value=f"[{rows} rows x {cols} columns] polars.dataframe.frame.DataFrame",
        kind=EnvironmentVariableValueKind.table,
        display_type=f"DataFrame [{rows}x{cols}]",
        type_info="polars.dataframe.frame.DataFrame",
        has_children=True,
        has_viewer=True,
        is_truncated=True,
        length=rows,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


def test_summarize_children_polars_dataframe() -> None:
    case = pl.DataFrame({"a": [1, 2], "b": ["3", "4"]})

    inspector = get_inspector(case)
    summary = inspector.summarize_children(case, _summarize_variable)

    assert_environment_variables_equal(
        summary,
        [
            not_none(_summarize_variable("a", case["a"])),
            not_none(_summarize_variable("b", case["b"])),
        ],
    )


def test_summarize_polars_series() -> None:
    case = pl.Series([0, 1])

    display_name = "xPolarsSeries"
    (rows,) = case.shape
    expected = EnvironmentVariable(
        display_name=display_name,
        display_value="[0, 1]",
        kind=EnvironmentVariableValueKind.map,
        display_type=f"Int64 [{rows}]",
        type_info="polars.series.series.Series",
        has_children=True,
        is_truncated=True,
        length=rows,
    )

    result = _summarize_variable(display_name, case)

    assert_environment_variable_equal(result, expected)


#
# End-to-end tests
#


# We purposefully use the kernel fixture instead of env_service or env_comm
# so that the comm is not yet opened.
def test_comm_open(kernel: PositronIPyKernel) -> None:
    env_service = kernel.env_service

    # Double-check that comm is not yet open
    assert env_service._comm is None

    # Open a comm
    env_comm = cast(DummyComm, comm.create_comm("positron.environment"))
    open_msg = {}
    env_service.on_comm_open(env_comm, open_msg)

    # Check that the comm_open and (empty) list messages were sent
    assert env_comm.messages == [
        {
            "data": {},
            "metadata": None,
            "buffers": None,
            "target_name": "positron.environment",
            "target_module": None,
            "msg_type": "comm_open",
        },
        {
            "data": {
                "msg_type": "list",
                "variables": [],
                "length": 0,
            },
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        },
    ]


@pytest.mark.parametrize(
    ("import_code", "value_codes"),
    [
        #
        # Same types
        #
        ("import numpy as np", [f"np.array({x})" for x in [3, [3], [[3]]]]),
        ("import torch", [f"torch.tensor({x})" for x in [3, [3], [[3]]]]),
        # TODO: Remove the `pytest.param` required to set `marks` once we fix https://github.com/posit-dev/positron/issues/609.
        pytest.param(
            "import pandas as pd",
            [f"pd.Series({x})" for x in [[], [3], [3, 3], ["3"]]],
            marks=pytest.mark.skip(reason="This is a known bug (#609)."),
        ),
        pytest.param(
            "import polars as pl",
            [f"pl.Series({x})" for x in [[], [3], [3, 3], ["3"]]],
            marks=pytest.mark.skip(reason="This is a known bug (#609)."),
        ),
        (
            "import pandas as pd",
            [
                f"pd.DataFrame({x})"
                for x in [{"a": []}, {"a": [3]}, {"a": ["3"]}, {"a": [3], "b": [3]}]
            ],
        ),
        (
            "import polars as pl",
            [
                f"pl.DataFrame({x})"
                for x in [{"a": []}, {"a": [3]}, {"a": ["3"]}, {"a": [3], "b": [3]}]
            ],
        ),
        #
        # Changing types
        #
        ("", ["3", "'3'"]),
        ("import numpy as np", ["3", "np.array(3)"]),
    ],
)
def test_change_detection(
    import_code: str,
    value_codes: List[str],
    shell: TerminalInteractiveShell,
    env_comm: DummyComm,
) -> None:
    """
    Test change detection when re-assigning values of the same type to the same name.
    """
    # Import the necessary library.
    shell.run_cell(import_code)

    for value_code in value_codes:
        # Assign the value to a variable.
        shell.run_cell(f"x = {value_code}")

        # Test that the expected `update` message was sent with the expected `assigned` value.
        assert env_comm.messages == [
            {
                "data": {
                    "msg_type": "update",
                    "assigned": [
                        not_none(_summarize_variable("x", shell.user_ns["x"])).dict(),
                    ],
                    "removed": set(),
                },
                "metadata": None,
                "buffers": None,
                "msg_type": "comm_msg",
            }
        ]

        # Clear messages for the next assignment.
        env_comm.messages.clear()


def test_handle_refresh(shell: TerminalInteractiveShell, env_comm: DummyComm) -> None:
    shell.user_ns.update({"x": 3})

    msg = {"content": {"data": {"msg_type": "refresh"}}}
    env_comm.handle_msg(msg)

    # A list message is sent
    assert env_comm.messages == [
        {
            "data": {
                "msg_type": "list",
                "variables": [
                    not_none(_summarize_variable("x", shell.user_ns["x"])).dict(),
                ],
                "length": 1,
            },
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        },
    ]


@pytest.mark.asyncio
async def test_handle_clear(
    shell: TerminalInteractiveShell, env_comm: DummyComm, kernel: PositronIPyKernel
) -> None:
    shell.user_ns.update({"x": 3, "y": 5})

    msg = {"msg_id": "0", "content": {"data": {"msg_type": "clear"}}}
    env_comm.handle_msg(msg)

    # Wait until all resulting kernel tasks are processed
    await asyncio.gather(*kernel._pending_tasks)

    # All user variables are removed
    assert "x" not in shell.user_ns
    assert "y" not in shell.user_ns

    # An update message (with the expected variables removed), and list message are sent
    assert env_comm.messages == [
        {
            "data": {"msg_type": "update", "assigned": [], "removed": {"x", "y"}},
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        },
        {
            "data": {"msg_type": "list", "variables": [], "length": 0},
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        },
    ]


def test_handle_delete(shell: TerminalInteractiveShell, env_comm: DummyComm) -> None:
    shell.user_ns.update({"x": 3, "y": 5})

    msg = {"content": {"data": {"msg_type": "delete", "names": ["x"]}}}
    env_comm.handle_msg(msg)

    # Only the `x` variable is removed
    assert "x" not in shell.user_ns
    assert "y" in shell.user_ns

    # An update message (with the expected variable removed) is sent
    assert env_comm.messages == [
        {
            "data": {"msg_type": "update", "assigned": [], "removed": {"x"}},
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        }
    ]


def test_handle_delete_error(env_comm: DummyComm) -> None:
    msg = {"content": {"data": {"msg_type": "delete", "names": ["x"]}}}
    env_comm.handle_msg(msg)

    # No messages are sent
    assert env_comm.messages == []


@pytest.mark.parametrize(
    "cls",
    [
        dict,
        pd.DataFrame,
        pd.Series,
        # We don't test polars series/dataframes here since they only supports string keys.
    ],
)
def test_handle_inspect_mixed_types(
    cls: Type, shell: TerminalInteractiveShell, env_comm: DummyComm
) -> None:
    """
    We should be able to inspect the children of a map/table with keys that have the same string representation.
    """
    value = cls({0: [0], "0": [1]})
    shell.user_ns.update({"x": value})

    for key in ["0", 0]:
        path = [encode_access_key("x"), encode_access_key(key)]
        msg = {"content": {"data": {"msg_type": "inspect", "path": path}}}
        env_comm.handle_msg(msg)

        inspector = get_inspector(value[key])

        assert env_comm.messages == [
            {
                "data": {
                    "msg_type": "details",
                    "path": path,
                    "children": inspector.summarize_children(value[key], _summarize_variable),
                    "length": 1,
                },
                "metadata": None,
                "buffers": None,
                "msg_type": "comm_msg",
            }
        ]

        env_comm.messages.clear()


def test_handle_inspect_error(env_comm: DummyComm) -> None:
    path = [encode_access_key("x")]
    msg = {"content": {"data": {"msg_type": "inspect", "path": path}}}
    env_comm.handle_msg(msg)

    # An error message is sent
    assert env_comm.messages == [
        {
            "data": {
                "msg_type": "error",
                "message": f"Cannot find variable at '{path}' to inspect",
            },
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        }
    ]


def test_handle_clipboard_format(shell: TerminalInteractiveShell, env_comm: DummyComm) -> None:
    shell.user_ns.update({"x": 3, "y": 5})

    msg = {
        "content": {
            "data": {
                "path": [encode_access_key("x")],
                "msg_type": "clipboard_format",
                "format": "text/plain",
                "data": "Hello, world!",
            }
        }
    }
    env_comm.handle_msg(msg)

    assert env_comm.messages == [
        {
            "data": {
                "msg_type": "formatted_variable",
                "format": "text/plain",
                "content": "3",
            },
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        },
    ]


def test_handle_clipboard_format_error(env_comm: DummyComm) -> None:
    path = [encode_access_key("x")]
    msg = {
        "content": {
            "data": {
                "path": path,
                "msg_type": "clipboard_format",
                "format": "text/plain",
                "data": "Hello, world!",
            }
        }
    }
    env_comm.handle_msg(msg)

    # An error message is sent
    assert env_comm.messages == [
        {
            "data": {
                "msg_type": "error",
                "message": f"Cannot find variable at '{path}' to format",
            },
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        }
    ]


def test_handle_view(
    shell: TerminalInteractiveShell, env_comm: DummyComm, kernel: PositronIPyKernel
) -> None:
    shell.user_ns.update({"x": pd.DataFrame({"a": [0]})})

    msg = {"content": {"data": {"msg_type": "view", "path": [encode_access_key("x")]}}}
    env_comm.handle_msg(msg)

    # No messages are sent over the environment comm
    assert env_comm.messages == []

    # A dataset and comm are added to the dataviewer service
    dataviewer_service = kernel.dataviewer_service
    id = next(iter(dataviewer_service.comms))
    dataset_comm = dataviewer_service.comms[id]
    dataset = dataviewer_service.datasets[id]

    # Check the dataset
    assert dataset == {
        "id": id,
        "title": "x",
        "columns": [{"name": "a", "type": "Series", "data": [0]}],
        "rowCount": 1,
    }

    # Check that the comm is open
    assert not dataset_comm._closed

    # TODO: test dataset viewer functionality here once it's ready


def test_handle_view_error(env_comm: DummyComm) -> None:
    path = [encode_access_key("x")]
    msg = {"content": {"data": {"msg_type": "view", "path": path}}}
    env_comm.handle_msg(msg)

    # An error message is sent
    assert env_comm.messages == [
        {
            "data": {
                "msg_type": "error",
                "message": f"Cannot find variable at '{path}' to view",
            },
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        }
    ]


def test_handle_unknown_message_type(env_comm: DummyComm) -> None:
    msg = {"content": {"data": {"msg_type": "unknown_msg_type"}}}
    env_comm.handle_msg(msg)

    assert env_comm.messages == [
        {
            "data": {
                "msg_type": "error",
                "message": "Unknown message type 'unknown_msg_type'",
            },
            "metadata": None,
            "buffers": None,
            "msg_type": "comm_msg",
        },
    ]


def test_shutdown(env_service: EnvironmentService) -> None:
    # Double-check that the comm is not yet closed
    env_comm = env_service._comm
    assert env_comm is not None
    assert not env_comm._closed

    env_service.shutdown()

    # Comm is closed
    assert env_comm._closed


@pytest.mark.parametrize(
    "case",
    BOOL_CASES
    + STRING_CASES
    + INT_CASES
    + NUMPY_SCALAR_CASES
    + FLOAT_CASES
    + COMPLEX_CASES
    + BYTES_CASES
    + RANGE_CASES
    + TIMESTAMP_CASES,
)
def test_encode_decode_access_key(case: Any) -> None:
    """
    Test that we can encode and decode to recovery supported data types.
    """
    access_key = encode_access_key(case)
    result = decode_access_key(access_key)
    # Handle the float('nan') case since nan != nan
    if isinstance(case, float) and math.isnan(case):
        assert math.isnan(result)
    else:
        assert result == case


@pytest.mark.parametrize(
    "case",
    [
        bytearray(),
        [],
        set(),
        L(),
        pd.DataFrame(),
        pd.Series(),
        pl.DataFrame(),
        pl.Series(),
        np.array([]),
    ],
)
def test_encode_access_key_not_hashable_error(case: Any) -> None:
    """
    Encoding an access key of an unhashable type raises an error.
    """
    with pytest.raises(TypeError):
        encode_access_key(case)


@pytest.mark.parametrize(
    "case",
    [
        torch.tensor([]),
        lambda x: x,
    ],
)
def test_encode_access_key_not_implemented_error(case: Any) -> None:
    """
    Encoding an access key of an unsupported type raises an error.
    """
    access_key = None

    with pytest.raises(NotImplementedError):
        access_key = encode_access_key(case)

    if access_key is not None:
        with pytest.raises(NotImplementedError):
            decode_access_key(access_key)


@pytest.mark.parametrize(
    "type_name",
    [
        "torch.Tensor",
        "function",
    ],
)
def test_decode_access_key_not_implemented_error(type_name: str) -> None:
    """
    Decoding an access key of an unsupported type raises an error.
    """
    access_key = json.dumps({"type": type_name, "data": None})
    with pytest.raises(NotImplementedError):
        decode_access_key(access_key)
