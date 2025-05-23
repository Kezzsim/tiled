import io
import mimetypes

from ..media_type_registration import (
    default_deserialization_registry,
    default_serialization_registry,
)
from ..structures.core import StructureFamily
from ..utils import APACHE_ARROW_FILE_MIME_TYPE, XLSX_MIME_TYPE, modules_available


@default_serialization_registry.register(
    StructureFamily.table, APACHE_ARROW_FILE_MIME_TYPE
)
def serialize_arrow(df, metadata, preserve_index=True):
    import pyarrow

    if isinstance(df, pyarrow.Table):
        table = df
    elif isinstance(df, dict):
        table = pyarrow.Table.from_pydict(df)
    else:
        table = pyarrow.Table.from_pandas(df, preserve_index=preserve_index)
    sink = pyarrow.BufferOutputStream()
    with pyarrow.ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)
    return memoryview(sink.getvalue())


@default_deserialization_registry.register(
    StructureFamily.table, APACHE_ARROW_FILE_MIME_TYPE
)
def deserialize_arrow(buffer):
    import pyarrow

    return pyarrow.ipc.open_file(buffer).read_pandas()


# There seems to be no official Parquet MIME type.
# https://issues.apache.org/jira/browse/PARQUET-1889
@default_serialization_registry.register(StructureFamily.table, "application/x-parquet")
def serialize_parquet(df, metadata, preserve_index=True):
    import pyarrow.parquet

    table = pyarrow.Table.from_pandas(df, preserve_index=preserve_index)
    sink = pyarrow.BufferOutputStream()
    with pyarrow.parquet.ParquetWriter(sink, table.schema) as writer:
        writer.write_table(table)
    return memoryview(sink.getvalue())


def serialize_csv(df, metadata, preserve_index=False):
    file = io.StringIO()
    df.to_csv(file, index=preserve_index)
    return file.getvalue().encode()


@default_deserialization_registry.register(StructureFamily.table, "text/csv")
def deserialize_csv(buffer):
    import pandas

    return pandas.read_csv(io.BytesIO(buffer), header=None)


default_serialization_registry.register(
    StructureFamily.table, "text/csv", serialize_csv
)
default_serialization_registry.register(
    StructureFamily.table, "text/x-comma-separated-values", serialize_csv
)
default_serialization_registry.register(
    StructureFamily.table, "text/plain", serialize_csv
)


@default_serialization_registry.register(StructureFamily.table, "text/html")
def serialize_html(df, metadata, preserve_index=False):
    file = io.StringIO()
    df.to_html(file, index=preserve_index)
    return file.getvalue().encode()


if modules_available("openpyxl", "pandas"):
    # The optional pandas dependency openpyxel is required for Excel read/write.
    import pandas

    @default_serialization_registry.register(StructureFamily.table, XLSX_MIME_TYPE)
    def serialize_excel(df, metadata, preserve_index=False):
        file = io.BytesIO()
        df.to_excel(file, index=preserve_index)
        return file.getbuffer()

    default_deserialization_registry.register(
        StructureFamily.table, XLSX_MIME_TYPE, pandas.read_excel
    )
    mimetypes.types_map.setdefault(".xlsx", XLSX_MIME_TYPE)
if modules_available("orjson"):
    import orjson

    default_serialization_registry.register(
        StructureFamily.table,
        "application/json",
        lambda df, metadata: orjson.dumps(
            {column: df[column].tolist() for column in df},
        ),
    )

    # Newline-delimited JSON. For example, this DataFrame:
    #
    # >>> pandas.DataFrame({"a": [1,2,3], "b": [4,5,6]})
    #
    # renders as this multi-line output:
    #
    # {'a': 1, 'b': 4}
    # {'a': 2, 'b': 5}
    # {'a': 3, 'b': 6}
    @default_serialization_registry.register(
        StructureFamily.table,
        "application/json-seq",  # official mimetype for newline-delimited JSON
    )
    def json_sequence(df, metadata):
        if rows := df.to_dict(orient="records"):
            # The first row is a special case; the rest start with a newline.
            yield orjson.dumps(rows[0])
            # Emit the remaining rows, prepending newline.
            for row in rows[1:]:
                yield b"\n" + orjson.dumps(row)
        else:
            # No rows
            yield b""


if modules_available("h5py"):
    from .container import serialize_hdf5

    default_serialization_registry.register(
        StructureFamily.table, "application/x-hdf5", serialize_hdf5
    )
