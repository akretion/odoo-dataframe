import io
from pathlib import Path

import polars as pl

from odoo import models
from odoo.exceptions import ValidationError
from odoo.modules.module import get_module_path

PARQUET_RELATIVE_SRC_DIR = "data/parquet"


class DfProcess(models.AbstractModel):
    _name = "df.process"
    _description = "Methods to process dataframe (abstract model)"

    def _subtitute_value_by_id(self, df, model, src_col, new_col, ref_col=None):
        """
        with this example:
            model: "res.partner"
            src_col: "client_code"
            new_col: "partner_id"
            ref_col: "ref"

        resulting dataframe will be like this:
        ┌──────────────┬─────────────┐
        │ client_code  ┆ partner_id  │
        ╞══════════════╪═════════════╡
        │ CODE1        ┆ CODE1       │  unknown partner_id
        │ CODE4        ┆ 2402        │  found partner_id
        │ CODE2        ┆ 9620        │  found
        │ CODE3        ┆ CODE3       │  unknown
        └──────────────┴─────────────┘
        """
        if ref_col is None:
            ref_col = src_col
        list_from_col = (
            df.select(pl.col(src_col).unique()).get_column(src_col).to_list()
        )
        domain = [(ref_col, "in", list_from_col)]
        map_ref_col = {
            x[ref_col]: str(x.id) for x in self.env[model].search(domain) if x[ref_col]
        }
        df = df.with_columns(
            pl.col(src_col).str.replace_many(map_ref_col).alias(new_col)
        )
        return df

    def _subtitute_value_by_id_and_split(
        self, df, model, src_col, new_col, ref_col=None, on_fail="skip"
    ):
        df = self._subtitute_value_by_id(df, model, src_col, new_col, ref_col=ref_col)
        unknown = df.filter(~pl.col(new_col).str.contains(r"^\d+$"))
        if on_fail == "skip":
            df = df.filter(pl.col(new_col).str.contains(r"^\d+$"))
            df = df.with_columns(pl.col(new_col).cast(pl.Int32).alias(new_col))
        return df, unknown

    def _df_filter_rows_when_no_numeric_val_in_column(self, df, column):
        """Exclude non numeric lines"""
        # Try to convert column to numeric, if not possible, set it to null
        df = df.with_columns(pl.col(column).cast(pl.Int64, strict=False))
        # Remove null lines
        new_df = df.filter(pl.col(column).is_not_null())
        excluded = df.filter(pl.col(column).is_null())
        return new_df, excluded

    def _store_dataframe(self, df):
        """Called with
        env["df.source"].browse(9).with_context(parquet=1).start()
        """
        self.ensure_one()

        def obfuscate(df):
            # TODO implements
            return df

        df = obfuscate(df)
        addon, file = self.env["df.source"]._get_addon_and_file_from_source_name()
        if addon != -1 and file != -1:
            file = file.replace(".sql", ".parquet")
            path = Path(get_module_path(addon)) / PARQUET_RELATIVE_SRC_DIR
            if not path.is_dir():
                raise ValidationError(f"'{path}' is not an existing directory")
            try:
                df.write_parquet(path / file)
            except Exception as err:
                raise ValidationError(f"Exception {err}") from err

    def _get_parquet_file_data(self, df):
        output = io.BytesIO()
        try:
            df.write_parquet(output)
        except Exception as err:
            raise ValidationError(f"Exception {err}") from err
        return output.getvalue()
