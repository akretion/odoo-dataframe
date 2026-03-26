import base64
import io
import logging

import polars as pl

logger = logging.getLogger(__name__)


class Df2Spreadsheet:
    def get_spreadsheet(self, df, settings=None, vals=None):
        # TODO depreceated, use get_spreadsheet instead
        file_stream = io.BytesIO()
        vals = vals or {}
        vals.update(self._get_spreadsheet_settings())
        vals.update({"workbook": file_stream})
        vals.update(settings)
        binary_cols = [k for k, v in df.schema.items() if v == pl.Binary]
        if binary_cols:
            df = df.drop(binary_cols)
            logger.warning(
                f"Binary '{binary_cols}' columns dropped from DataFrame "
                "as they are not supported in Excel."
            )
        df.write_excel(**vals)
        file_stream.seek(0)
        return base64.encodebytes(file_stream.read())

    @staticmethod
    def _get_spreadsheet_settings():
        return {
            "position": "A1",
            "table_style": "Table Style Light 8",
            "dtype_formats": {pl.Date: "dd/mm/yyyy"},
            "float_precision": 3,
            "header_format": {"bold": True, "font_color": "#702963"},
            "freeze_panes": "A2",
            "autofit": True,
        }
